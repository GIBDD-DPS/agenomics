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

from genome_from_capture import derive_genome_from_capture


def _genome_hash(genome) -> str:
    """Тот же принцип, что в agenomics.ledger: детерминированный хэш
    по значениям полей, для provenance в AEP-001."""
    payload = {
        "domain": genome.domain, "autonomy": genome.autonomy.value if hasattr(genome.autonomy, "value") else genome.autonomy,
        "data_safety": genome.data_safety, "drift_rate": genome.drift_rate, "has_ledger": genome.has_ledger,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _load_history_from_store(store: EvidenceStore, agent_id: str):
    """Восстанавливает историю прогонов из файла базы, а не из памяти
    процесса. Переживает перезапуск между запусками CI.

    Наблюдения без execution_status (записанные до этой версии или из
    другого источника) просто пропускаются, а не подставляются фиктивным
    значением. Лучше меньше истории, чем искажённая."""
    statuses, durations = [], []
    for obs in store.get_observations(agent_id):
        if obs.execution_status is not None:
            statuses.append(obs.execution_status)
            if obs.duration_seconds is not None:
                durations.append(obs.duration_seconds)
    return statuses, durations


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
) -> dict:
    """Один вызов делает всё: запускает агента, захватывает лог, строит
    честный геном, считает настоящий TrustScorer.score() и записывает
    результат в EvidenceStore со всеми полями AEP-001 (genome_hash,
    evaluation_period, collector, source, execution_status,
    duration_seconds) и реальными инцидентами.

    Возвращает словарь со сводкой: status, score, label, confidence,
    leaked_secrets."""
    import io, contextlib, logging, time
    from datetime import timezone
    from agenomics import Incident, IncidentCategory, IncidentSeverity, IncidentSource

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

    try:
        with contextlib.redirect_stdout(stream):
            run_fn()
    except Exception:
        status = "error"
    finally:
        for name in loggers:
            logging.getLogger(name).removeHandler(handler)

    duration = round(time.perf_counter() - start_perf, 3)
    raw_log = stream.getvalue()

    # История грузится из store до текущего прогона, затем текущий
    # прогон добавляется к ней локально для передачи в genome_from_capture.
    # Запись в store ниже (не какой-либо словарь в памяти) и есть то,
    # что переживает перезапуск процесса.
    past_statuses, past_durations = _load_history_from_store(store, framework)
    history_statuses = past_statuses + [status]
    history_durations = past_durations + [duration]

    derivation = derive_genome_from_capture(
        framework, raw_log, domain=domain, autonomy=autonomy, has_ledger=has_ledger,
        framework_history_statuses=history_statuses,
        framework_history_durations=history_durations,
    )
    genome = derivation.genome

    result = TrustScorer(weight_profile=weight_profile).score(genome)

    incidents = []
    if status == "error":
        incidents.append(Incident(
            description=f"Framework {framework}: исключение при выполнении",
            severity=IncidentSeverity.SEVERE, category=IncidentCategory.OTHER,
            source=IncidentSource.AUTOMATED_MONITOR, confirmed=True,
        ))
    for secret_type in derivation.leaked_secret_types:
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
        source="full_pipeline.py",
        execution_status=status,
        duration_seconds=duration,
        incidents=incidents,
        timestamp=started_at,
    )

    if print_report:
        print(trust_report(result, agent_id=framework))
        if derivation.derivation_notes:
            print("\nЗаметки о выводе генома:")
            for note in derivation.derivation_notes:
                print(f"  - {note}")
        print(f"\nИстория для predictability: {len(history_statuses)} прогонов "
              f"(включая {len(past_statuses)} из предыдущих запусков процесса)")

    return {
        "framework": framework, "status": status, "score": result.score,
        "label": result.label, "confidence": result.confidence,
        "leaked_secrets": derivation.leaked_secret_types,
    }
