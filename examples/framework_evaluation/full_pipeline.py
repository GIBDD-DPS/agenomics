# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
full_pipeline.py. Склеивает захват лога, построение генома, TrustScorer
и запись в EvidenceStore в один вызов.

Проект: Prizolov Lab

Раньше история для predictability хранилась в словаре на уровне модуля,
и он жил только в памяти одного процесса. В GitHub Actions каждый запуск
это новый процесс, поэтому история никогда не накапливалась между
запусками, хотя README обещал обратное. Теперь история загружается из
самого EvidenceStore перед каждым построением генома, никакого состояния
в памяти, которое можно потерять.

Пример:
    from full_pipeline import run_framework_and_record

    run_framework_and_record(
        "langchain", lambda: my_langchain_agent.run(task),
        domain="content", autonomy="advisory", store=store,
    )
"""

import hashlib
import json
from datetime import datetime
from typing import Callable, List, Optional

from agenomics import EvidenceStore, TrustScorer, trust_report

from classify_failures import classify_error
from genome_from_capture import SECRET_SCANNER_VERSION, _detect_leaked_secrets, derive_genome_pre_run

# Помечает наблюдения, чей score посчитан ДО прогона (v0.7.12+). Записи
# с source="full_pipeline.py" (без суффикса) сделаны старой версией,
# где score считался по логу и статусу того же прогона, что и его
# инциденты. Для проверки связи score с инцидентами их нужно исключать,
# см. CHANGELOG 0.7.12.
PRE_RUN_SOURCE = "full_pipeline.py/pre-run"

# Классы из classify_failures.classify_error(), которые означают сбой
# окружения, а не поведения агента. "timeout" сюда сознательно не
# входит: таймаут бывает и у провайдера, и у агента, зациклившегося на
# задаче, и по тексту исключения их не отличить.
_INFRASTRUCTURE_ERROR_CLASSES = {
    "rate_limit", "import_error", "model_unavailable", "auth_error",
    "provider_routing_error", "known_upstream_bug",
}

# AEP-001 (Privacy) предупреждает о description длиннее 200 символов.
_MAX_DESCRIPTION = 200

# [v0.9.0] Тяжесть инцидента по классу ошибки. До v0.9.0 любая ошибка
# была SEVERE, и в базе rate limit весил столько же, сколько утечка
# ключа. Нераспознанная ошибка ("other") остаётся SEVERE: это может быть
# сбой самого агента, и занижать её без оснований нельзя.
_SEVERITY_BY_ERROR_CLASS = {
    "rate_limit": "minor",
    "timeout": "moderate",
    "provider_routing_error": "moderate",
    "model_unavailable": "moderate",
    "auth_error": "moderate",
    "import_error": "moderate",
    "known_upstream_bug": "moderate",
}

# [v0.9.0] Доноры доказательств этого пайплайна (AEP-001 v1.1). Независимы
# друг от друга: runtime-монитор смотрит на исключения и время, сканер на
# текст лога. Оба автоматические, поэтому ни один не даёт Q3/Q4.
RUNTIME_DONOR = dict(
    donor_id="framework_eval.runtime_monitor", donor_type="execution",
    name="framework_evaluation runtime monitor", independence_group="runtime",
)
SCANNER_DONOR = dict(
    donor_id=f"framework_eval.secret_scanner.v{SECRET_SCANNER_VERSION}", donor_type="security",
    name="framework_evaluation regex secret scanner", independence_group="regex_secret_scanner",
    version=SECRET_SCANNER_VERSION,
)

# [v0.9.2] Третий донор: проверка ответа агента для шаблонов, у задачи
# которых есть однозначный правильный ответ (функция check() в шаблоне).
# Детерминированная проверка реального исхода задачи, поэтому Q3
# ("подтверждённый автоматический исход"), выше runtime (Q1) и сканера (Q2).
TASK_CHECKER_DONOR = dict(
    donor_id="framework_eval.task_checker", donor_type="outcome",
    name="framework_evaluation deterministic answer check", independence_group="task_checker",
)

# [v0.9.2] Что предсказывает замороженный Trust Score. До v0.9.2 была одна
# цель incident_in_run, в которой смешивались отказ выполнения, утечка и
# (в task_outcome) результат задачи. Теперь у каждого прогона отдельное
# предсказание на каждую цель, и Validation Engine проверяет их порознь:
# один и тот же score может предсказывать утечки и не предсказывать отказы.
TARGET_RUNTIME = "runtime_failure"      # исход execution_error от runtime-монитора
TARGET_SECURITY = "security_incident"   # исход secret_leak от сканера
TARGET_TASK = "task_failure"            # исход task_failure от task_checker, только если есть check()
PREDICTION_HORIZON = "current_run"

# Где в результатах разных фреймворков обычно лежит идентификатор модели,
# которую реально вернул провайдер: LangChain AIMessage.response_metadata
# ["model_name"], OpenAI-совместимый ответ .model, вложенные messages/
# choices/raw. Список эвристический: для фреймворка, чей результат не
# содержит модель ни в одном из этих мест, observed_model_version честно
# остаётся None, а не подставляется заявленная.
_MODEL_KEYS = ("model_name", "model", "model_id")
_CONTAINER_KEYS = (
    "response_metadata", "messages", "choices", "raw", "response", "output",
    "result", "message", "messages_history", "run_response",
)
_MAX_SEARCH_DEPTH = 5


def _framework_version(package: Optional[str]) -> Optional[str]:
    """"<пакет>==<версия>" установленной библиотеки фреймворка, None, если
    пакет не задан или не установлен."""
    if not package:
        return None
    from importlib.metadata import PackageNotFoundError, version
    try:
        return f"{package}=={version(package)}"
    except PackageNotFoundError:
        return None


def _looks_like_model_id(value) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 200 and not any(c.isspace() for c in value)


def _safe_getattr(obj, name: str):
    """getattr, не пропускающий наружу исключения чужих property: поиск
    модели не должен ронять запись прогона, который уже отработал."""
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def _find_model_id(obj, depth: int = 0) -> Optional[str]:
    """Ищет идентификатор модели в результате run(), см. _MODEL_KEYS."""
    if obj is None or depth > _MAX_SEARCH_DEPTH or isinstance(obj, (str, bytes, int, float, bool)):
        return None
    if isinstance(obj, dict):
        getter, keys = obj.get, obj.keys()
    else:
        getter, keys = (lambda k: _safe_getattr(obj, k)), None
    for key in _MODEL_KEYS:
        if keys is not None and key not in keys:
            continue
        value = getter(key)
        if _looks_like_model_id(value):
            return value
    for key in _CONTAINER_KEYS:
        if keys is not None and key not in keys:
            continue
        found = _find_model_id(getter(key), depth + 1)
        if found:
            return found
    if isinstance(obj, (list, tuple)):
        # С конца: в истории сообщений ответ модели обычно последний.
        for item in reversed(obj[-5:]):
            found = _find_model_id(item, depth + 1)
            if found:
                return found
    return None


def _model_matches(declared: Optional[str], observed: Optional[str]) -> Optional[bool]:
    """MODEL_VERSION пишется как "<провайдер>/<модель>", а провайдер в
    ответе обычно возвращает только "<модель>" (например, Groq отвечает
    "openai/gpt-oss-20b" на "groq/openai/gpt-oss-20b"). Совпадением
    считается, если одно оканчивается другим. None: сравнивать не с чем."""
    if not declared or not observed:
        return None
    declared, observed = declared.lower(), observed.lower()
    return declared.endswith(observed) or observed.endswith(declared)


def _configuration_hash(**configuration) -> str:
    """[v0.9.0] Хэш конфигурации агента, а не его текущего состояния.

    До v0.9.0 genome_hash считался по всем полям AgentGenome, включая
    drift_rate и axis_confidence, которые выводятся из истории прогонов
    и меняются почти каждый прогон (хотя бы из-за разброса длительности).
    Итог: у одного агента за 59 прогонов было ~40 "разных геномов", и
    число уникальных геномов в отчёте выглядело как разнообразие, хотя
    независимых агентов было 19. Теперь хэш меняется только тогда, когда
    меняется то, что делает агента другим агентом: фреймворк, его версия,
    модель, промпт, домен, автономность, ledger."""
    return hashlib.sha256(json.dumps(
        configuration, sort_keys=True, default=str,
    ).encode()).hexdigest()[:16]


def _is_infrastructure_failure(obs) -> bool:
    """Упал ли прогон из-за окружения, а не агента. Для данных до 0.7.12,
    где категории infrastructure ещё не было, класс восстанавливается по
    тексту инцидента тем же classify_error()."""
    for inc in obs.incidents:
        category = inc.get("category")
        if category == "infrastructure":
            return True
        if category in (None, "other") and classify_error(inc.get("description") or "") in _INFRASTRUCTURE_ERROR_CLASSES:
            return True
    return False


def _load_history_from_store(store: EvidenceStore, agent_id: str):
    """Восстанавливает историю прогонов из файла базы, а не из памяти
    процесса. Переживает перезапуск между запусками CI.

    Наблюдения без execution_status (записанные до этой версии или из
    другого источника) просто пропускаются, а не подставляются фиктивным
    значением. Лучше меньше истории, чем искажённая.

    Возвращает статусы и длительности для predictability, по одному bool
    на прогон, была ли в нём найдена утечка секрета, и надёжность запуска.

    [v0.9.0] Прогоны, упавшие из-за окружения (ImportError, нет ключа,
    rate limit), в predictability не входят: это свойство CI и
    зависимостей, а не агента, и до v0.9.0 оно занижало Trust Score
    четырёх фреймворков, которые ни разу не запустились. Они учитываются
    отдельно, в runtime_reliability. Утечки считаются по всем прогонам.

    runtime_reliability: доля успешных прогонов среди всех, включая
    упавшие из-за окружения; None, если прогонов не было."""
    statuses, durations, leaks = [], [], []
    n_runs = n_success = 0
    for obs in store.get_observations(agent_id):
        if obs.execution_status is None:
            continue
        n_runs += 1
        n_success += obs.execution_status == "success"
        leaks.append(any(inc.get("category") == "data_leak" for inc in obs.incidents))
        if obs.execution_status == "error" and _is_infrastructure_failure(obs):
            continue
        statuses.append(obs.execution_status)
        if obs.duration_seconds is not None:
            durations.append(obs.duration_seconds)
    runtime_reliability = round(n_success / n_runs, 3) if n_runs else None
    return statuses, durations, leaks, runtime_reliability


def run_framework_and_record(
    framework: str,
    run_fn: Callable,
    store: EvidenceStore,
    domain: Optional[str] = None,
    autonomy: str = "advisory",
    has_ledger: bool = False,
    weight_profile: str = "default",
    loggers: Optional[List[str]] = None,
    print_report: bool = True,
    model_version: Optional[str] = None,
    prompt_version: Optional[str] = None,
    framework_package: Optional[str] = None,
    check_fn: Optional[Callable] = None,
) -> dict:
    """Один вызов делает всё: строит геном из истории прошлых прогонов и
    считает по нему TrustScorer.score() ДО запуска, затем запускает
    агента, захватывает лог и записывает
    результат в EvidenceStore со всеми полями AEP-001 (genome_hash,
    evaluation_period, collector, source, execution_status,
    duration_seconds, model_version, prompt_version) и реальными
    инцидентами.

    Возвращает словарь со сводкой: status, score, label, confidence,
    leaked_secrets, error_class, framework_version, observed_model_version,
    model_match (True/False, None если модель в ответе не найдена),
    runtime_reliability (доля успешных прогонов, включая этот),
    task_check (True/False, None если проверки нет или она не выполнилась),
    observation_id, prediction_ids ({target: id}).

    check_fn(result) -> bool: проверка итогового ответа агента для задач
    с однозначным правильным ответом. Без неё предсказание task_failure
    не создаётся, а task_outcome остаётся неизвестным при успешном прогоне."""
    import io, contextlib, logging, time
    from datetime import timezone
    from agenomics import Incident, IncidentCategory, IncidentSeverity, IncidentSource

    # Score фиксируется до прогона, только из прошлых прогонов. Всё, что
    # случится в текущем прогоне (статус, длительность, утечка в логе),
    # попадает в наблюдение как исход, но не влияет на его score:
    # иначе score и инциденты одного наблюдения зависят от одного и того
    # же события, и их корреляция ничего не доказывает (target leakage).
    past_statuses, past_durations, past_leaks, past_reliability = _load_history_from_store(store, framework)
    derivation = derive_genome_pre_run(
        framework, domain=domain, autonomy=autonomy, has_ledger=has_ledger,
        framework_history_statuses=past_statuses,
        framework_history_durations=past_durations,
        framework_history_leaks=past_leaks,
    )
    genome = derivation.genome
    result = TrustScorer(weight_profile=weight_profile).score(genome)
    scored_at = datetime.now(timezone.utc)

    # [v0.9.0] Наблюдение и предсказание пишутся в базу ДО запуска
    # агента, исход дописывается после. Если процесс упадёт посередине,
    # в базе останется предсказание без исхода: честное "исход неизвестен",
    # а не запись, собранная задним числом.
    framework_version = _framework_version(framework_package)
    obs_id = store.record_observation(
        agent_id=framework,
        declared_score=result.score,
        declared_label=result.label,
        declared_confidence=result.confidence,
        genome_hash=_configuration_hash(
            framework=framework, framework_version=framework_version, model_version=model_version,
            prompt_version=prompt_version, domain=domain, autonomy=autonomy, has_ledger=has_ledger,
        ),
        trust_model_version=None,  # проставится текущей версией agenomics
        evaluation_period=scored_at.isoformat(),
        request_count=1,
        collector="sdk",
        source=PRE_RUN_SOURCE,
        model_version=model_version,
        prompt_version=prompt_version,
        framework_version=framework_version,
        timestamp=scored_at,
    )
    store.register_donor(**RUNTIME_DONOR)
    store.register_donor(**SCANNER_DONOR)
    targets = [TARGET_RUNTIME, TARGET_SECURITY]
    if check_fn is not None:
        store.register_donor(**TASK_CHECKER_DONOR)
        targets.append(TARGET_TASK)
    prediction_ids = {
        target: store.record_prediction(obs_id, target=target, horizon=PREDICTION_HORIZON, frozen_at=scored_at)
        for target in targets
    }

    loggers = loggers or [""]
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    for name in loggers:
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).setLevel(logging.DEBUG)

    start_perf = time.perf_counter()
    status = "success"
    error_summary = None
    error_class = None
    run_result = None

    try:
        with contextlib.redirect_stdout(stream):
            run_result = run_fn()
    except Exception as exc:
        status = "error"
        # Раньше текст исключения нигде не сохранялся, инцидент содержал
        # только шаблонное "исключение при выполнении" без единой детали.
        # Найдено при разборе первого прогона всех 29 фреймворков: было
        # невозможно понять, упал ли фреймворк из-за отсутствия
        # OPENAI_API_KEY, ImportError или чего-то ещё. Обрезаем до 300
        # символов, чтобы длинный traceback не раздувал Incident.description.
        error_summary = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        for name in loggers:
            logging.getLogger(name).removeHandler(handler)

    duration = round(time.perf_counter() - start_perf, 3)
    raw_log = stream.getvalue()

    # Исход текущего прогона. Попадает в store и станет историей для
    # score следующего прогона, но не для score этого.
    leaked_secret_types = _detect_leaked_secrets(raw_log)

    incidents = []
    if status == "error":
        # Класс ошибки пишется при записи, а не только при чтении отчёта
        # (classify_failures.py): ImportError и отсутствующий ключ не
        # должны выглядеть в базе так же, как сбой поведения агента.
        error_class = classify_error(error_summary)
        category = (
            IncidentCategory.INFRASTRUCTURE if error_class in _INFRASTRUCTURE_ERROR_CLASSES
            else IncidentCategory.OTHER
        )
        incidents.append(Incident(
            description=f"[{error_class}] Framework {framework}: {error_summary}"[:_MAX_DESCRIPTION],
            severity=IncidentSeverity(_SEVERITY_BY_ERROR_CLASS.get(error_class, "severe")), category=category,
            source=IncidentSource.AUTOMATED_MONITOR, confirmed=True,
        ))
    for secret_type in leaked_secret_types:
        incidents.append(Incident(
            description=f"Обнаружена возможная утечка секрета: {secret_type}",
            severity=IncidentSeverity.SEVERE, category=IncidentCategory.DATA_LEAK,
            source=IncidentSource.AUTOMATED_MONITOR, confirmed=True,  # паттерн реально найден, не догадка
        ))

    observed_model_version = _find_model_id(run_result)
    model_match = _model_matches(model_version, observed_model_version)
    is_infrastructure = error_class in _INFRASTRUCTURE_ERROR_CLASSES

    # Проверка ответа. Ошибка самой проверки (неожиданная форма результата)
    # это "исход неизвестен", а не провал задачи: иначе баг проверки
    # выглядел бы как плохое поведение агента.
    task_check = None
    task_check_error = None
    if check_fn is not None and status == "success":
        try:
            task_check = bool(check_fn(run_result))
        except Exception as exc:
            task_check_error = f"{type(exc).__name__}: {exc}"[:150]

    # task_outcome (v0.9.2) описывает только задачу: упал прогон, значит
    # задача не выполнена; есть проверка, значит её результат; иначе
    # неизвестно. Утечка секрета это отдельный исход (security_incident),
    # а не провал задачи, как было до v0.9.2.
    #
    # [v0.9.5] Прогон, упавший из-за окружения (нет ключа, не ставится
    # библиотека, rate limit), это "исход неизвестен", а не провал задачи:
    # агент до задачи не дошёл. До v0.9.5 здесь писалось "failure", и
    # колонка task_outcome противоречила графу доказательств, где у того
    # же прогона infrastructure_error.
    if status == "error":
        task_outcome = None if is_infrastructure else "failure"
    elif task_check is not None:
        task_outcome = "success" if task_check else "failure"
    else:
        task_outcome = None

    store.record_execution(obs_id, status, duration, observed_model_version=observed_model_version)
    if task_outcome is not None:
        store.record_task_outcome(obs_id, task_outcome, incidents)
    elif incidents:
        store.add_incidents(obs_id, incidents)

    # Доказательства и исходы от каждого донора отдельно: доноры не
    # подтверждают друг друга, они смотрят на разное.
    reference = f"framework_eval:{framework}:{scored_at.isoformat()}"
    store.record_evidence(
        obs_id, RUNTIME_DONOR["donor_id"], "execution",
        "success" if status == "success" else f"error:{error_class}", "Q1", source_reference=reference,
    )
    store.record_evidence(
        obs_id, SCANNER_DONOR["donor_id"], "secret_scan",
        "leak:" + ",".join(leaked_secret_types) if leaked_secret_types else "clean", "Q2",
        source_reference=reference,
    )
    if check_fn is not None:
        if status == "error":
            finding = "not_run"
        elif task_check_error:
            finding = f"check_error:{task_check_error}"
        else:
            finding = "pass" if task_check else "fail"
        store.record_evidence(
            obs_id, TASK_CHECKER_DONOR["donor_id"], "task_check", finding, "Q3", source_reference=reference,
        )

    for target, prediction_id in prediction_ids.items():
        # Прогон, упавший из-за окружения, помечается у КАЖДОЙ цели: агент
        # не работал, и Validation Engine должен исключить все его
        # предсказания, а не только runtime (иначе "утечки не было" в
        # непрогнанном агенте выглядело бы как подтверждение безопасности).
        if is_infrastructure:
            store.record_outcome(prediction_id, RUNTIME_DONOR["donor_id"], "infrastructure_error", occurred=True)
            continue
        if target == TARGET_RUNTIME:
            store.record_outcome(prediction_id, RUNTIME_DONOR["donor_id"], "execution_error", occurred=status == "error")
        elif target == TARGET_SECURITY:
            store.record_outcome(prediction_id, SCANNER_DONOR["donor_id"], "secret_leak", occurred=bool(leaked_secret_types))
        elif target == TARGET_TASK and task_outcome is not None:
            store.record_outcome(prediction_id, TASK_CHECKER_DONOR["donor_id"], "task_failure",
                                 occurred=task_outcome == "failure")

    runs_total = len(past_leaks) + 1
    runtime_reliability = round(
        ((past_reliability or 0.0) * len(past_leaks) + (status == "success")) / runs_total, 3,
    )

    if print_report:
        print(trust_report(result, agent_id=framework))
        if derivation.derivation_notes:
            print("\nЗаметки о выводе генома:")
            for note in derivation.derivation_notes:
                print(f"  - {note}")
        print(f"\nScore посчитан до прогона по истории из {len(past_statuses)} прошлых прогонов "
              f"(без упавших из-за окружения); надёжность запуска: {runtime_reliability:.0%}")

    return {
        "framework": framework, "status": status, "score": result.score,
        "label": result.label, "confidence": result.confidence,
        "leaked_secrets": leaked_secret_types,
        "error_class": error_class,
        "error_summary": error_summary,
        "task_check_error": task_check_error,
        "framework_version": framework_version,
        "observed_model_version": observed_model_version,
        "model_match": model_match,
        "runtime_reliability": runtime_reliability,
        "task_check": task_check,
        "observation_id": obs_id,
        "prediction_ids": prediction_ids,
    }
