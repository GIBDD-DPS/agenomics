"""
full_pipeline.py — полная интеграция: capture_log_v2 -> genome_from_capture
-> TrustScorer -> EvidenceStore, с честным AEP-001-видом данных.

Автор: доработка для интеграции с Agenomics
Проект: Prizolov Lab

Использование:
    from full_pipeline import run_framework_and_record

    run_framework_and_record(
        "langchain", lambda: my_langchain_agent.run(task),
        domain="content", autonomy="advisory", store=store,
    )
"""

import hashlib
import json
from datetime import datetime
from typing import Callable, Dict, List, Optional

from agenomics import EvidenceStore, TrustScorer, trust_report

from genome_from_capture import derive_genome_from_capture

# История прогонов по framework — нужна для predictability (см.
# genome_from_capture._derive_predictability_from_history). In-memory
# на время сессии; при желании можно подгружать из EvidenceStore заранее.
_HISTORY: Dict[str, Dict[str, List]] = {}


def _genome_hash(genome) -> str:
    """Тот же принцип, что и в agenomics.ledger — детерминированный хэш
    по значениям полей, для provenance в AEP-001."""
    payload = {
        "domain": genome.domain, "autonomy": genome.autonomy.value if hasattr(genome.autonomy, "value") else genome.autonomy,
        "data_safety": genome.data_safety, "drift_rate": genome.drift_rate, "has_ledger": genome.has_ledger,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def run_framework_and_record(
    framework: str,
    run_fn: Callable,
    store: EvidenceStore,
    domain: Optional[str] = None,
    autonomy: str = "advisory",
    weight_profile: str = "default",
    loggers: Optional[List[str]] = None,
    print_report: bool = True,
) -> dict:
    """
    Один вызов = полный цикл: запуск -> захват лога -> честный геном ->
    настоящий TrustScorer.score() -> запись в EvidenceStore с полным
    набором полей AEP-001 (genome_hash, evaluation_period, collector,
    source) и настоящими инцидентами (не placeholder 100/0, как в
    первой версии импортёра).

    Возвращает сводку {status, score, label, confidence, leaked_secrets}.
    """
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

    # --- Обновляем историю ПЕРЕД построением генома (текущий прогон
    # тоже должен участвовать в оценке predictability) ---
    hist = _HISTORY.setdefault(framework, {"statuses": [], "durations": []})
    hist["statuses"].append(status)
    hist["durations"].append(duration)

    derivation = derive_genome_from_capture(
        framework, raw_log, domain=domain, autonomy=autonomy,
        framework_history_statuses=hist["statuses"],
        framework_history_durations=hist["durations"],
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
        trust_model_version=None,  # проставится автоматически текущей версией agenomics
        evaluation_period=started_at.isoformat(),
        request_count=1,
        collector="sdk",
        source="full_pipeline.py",
        incidents=incidents,
        timestamp=started_at,
    )

    if print_report:
        print(trust_report(result, agent_id=framework))
        if derivation.derivation_notes:
            print("\nЗаметки о выводе генома:")
            for note in derivation.derivation_notes:
                print(f"  - {note}")

    return {
        "framework": framework, "status": status, "score": result.score,
        "label": result.label, "confidence": result.confidence,
        "leaked_secrets": derivation.leaked_secret_types,
    }
