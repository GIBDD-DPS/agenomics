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
from genome_from_capture import _detect_leaked_secrets, derive_genome_pre_run

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


def _genome_hash(genome) -> str:
    """Тот же принцип, что в agenomics.ledger: детерминированный хэш
    по всем полям датакласса, не по вручную поддерживаемому списку.

    Раньше здесь был короткий ручной список из 5 полей (domain,
    autonomy, data_safety, drift_rate, has_ledger), и два генома,
    различающихся, например, только transparency или axis_confidence,
    получали одинаковый хэш. Та же находка, что и в agenomics.ledger,
    исправлена тем же способом: dataclasses.asdict() автоматически
    охватывает все текущие и будущие поля AgentGenome."""
    from dataclasses import asdict
    payload = asdict(genome)
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True,
        default=lambda o: getattr(o, "value", str(o)),
    ).encode()).hexdigest()[:16]


def _load_history_from_store(store: EvidenceStore, agent_id: str):
    """Восстанавливает историю прогонов из файла базы, а не из памяти
    процесса. Переживает перезапуск между запусками CI.

    Наблюдения без execution_status (записанные до этой версии или из
    другого источника) просто пропускаются, а не подставляются фиктивным
    значением. Лучше меньше истории, чем искажённая.

    Возвращает статусы, длительности и, по одному bool на прогон, была
    ли в нём найдена утечка секрета (инцидент категории data_leak)."""
    statuses, durations, leaks = [], [], []
    for obs in store.get_observations(agent_id):
        if obs.execution_status is not None:
            statuses.append(obs.execution_status)
            if obs.duration_seconds is not None:
                durations.append(obs.duration_seconds)
            leaks.append(any(inc.get("category") == "data_leak" for inc in obs.incidents))
    return statuses, durations, leaks


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
) -> dict:
    """Один вызов делает всё: строит геном из истории прошлых прогонов и
    считает по нему TrustScorer.score() ДО запуска, затем запускает
    агента, захватывает лог и записывает
    результат в EvidenceStore со всеми полями AEP-001 (genome_hash,
    evaluation_period, collector, source, execution_status,
    duration_seconds, model_version, prompt_version) и реальными
    инцидентами.

    Возвращает словарь со сводкой: status, score, label, confidence,
    leaked_secrets."""
    import io, contextlib, logging, time
    from datetime import timezone
    from agenomics import Incident, IncidentCategory, IncidentSeverity, IncidentSource

    # Score фиксируется до прогона, только из прошлых прогонов. Всё, что
    # случится в текущем прогоне (статус, длительность, утечка в логе),
    # попадает в наблюдение как исход, но не влияет на его score:
    # иначе score и инциденты одного наблюдения зависят от одного и того
    # же события, и их корреляция ничего не доказывает (target leakage).
    past_statuses, past_durations, past_leaks = _load_history_from_store(store, framework)
    derivation = derive_genome_pre_run(
        framework, domain=domain, autonomy=autonomy, has_ledger=has_ledger,
        framework_history_statuses=past_statuses,
        framework_history_durations=past_durations,
        framework_history_leaks=past_leaks,
    )
    genome = derivation.genome
    result = TrustScorer(weight_profile=weight_profile).score(genome)

    loggers = loggers or [""]
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    for name in loggers:
        logging.getLogger(name).addHandler(handler)
        logging.getLogger(name).setLevel(logging.DEBUG)

    started_at = datetime.now(timezone.utc)
    start_perf = time.perf_counter()
    status = "success"
    error_summary = None

    try:
        with contextlib.redirect_stdout(stream):
            run_fn()
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
            description=f"[{error_class}] Framework {framework}: {error_summary}",
            severity=IncidentSeverity.SEVERE, category=category,
            source=IncidentSource.AUTOMATED_MONITOR, confirmed=True,
        ))
    for secret_type in leaked_secret_types:
        incidents.append(Incident(
            description=f"Обнаружена возможная утечка секрета: {secret_type}",
            severity=IncidentSeverity.SEVERE, category=IncidentCategory.DATA_LEAK,
            source=IncidentSource.AUTOMATED_MONITOR, confirmed=True,  # паттерн реально найден, не догадка
        ))

    store.record_observation(
        agent_id=framework,
        declared_score=result.score,
        declared_label=result.label,
        declared_confidence=result.confidence,
        genome_hash=_genome_hash(genome),
        trust_model_version=None,  # проставится текущей версией agenomics
        evaluation_period=started_at.isoformat(),
        request_count=1,
        collector="sdk",
        source=PRE_RUN_SOURCE,
        execution_status=status,
        duration_seconds=duration,
        model_version=model_version,
        prompt_version=prompt_version,
        incidents=incidents,
        timestamp=started_at,
    )

    if print_report:
        print(trust_report(result, agent_id=framework))
        if derivation.derivation_notes:
            print("\nЗаметки о выводе генома:")
            for note in derivation.derivation_notes:
                print(f"  - {note}")
        print(f"\nScore посчитан до прогона по истории из {len(past_statuses)} прошлых прогонов")

    return {
        "framework": framework, "status": status, "score": result.score,
        "label": result.label, "confidence": result.confidence,
        "leaked_secrets": leaked_secret_types,
    }
