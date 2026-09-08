"""
hooks.py. Готовая реализация AgentLifecycleHook поверх EvidenceStore.

Проект: Prizolov Lab

Контекст: интерфейс AgentLifecycleHook (docs/PRIZOLOV_BRIDGE_INTERFACE.md)
описывает, что внешний оркестратор мог бы вызывать на разных этапах
жизненного цикла агента.

Использование (когда сигнатуры Prizolov Market появятся, интеграция
сведётся к трём вызовам в нужных местах вашего оркестратора):

    hook = EvidenceStoreHook(EvidenceStore("agenomics_evidence.db"))
    hook.on_trust_scored("agent-1", result)
    hook.on_drift_alert("agent-1", drift_report)
"""

from datetime import datetime, timezone
from typing import Optional

from .drift import DriftReportV2
from .evidence import EvidenceStore
from .feedback import Incident, IncidentCategory, IncidentSeverity, IncidentSource
from .trust_score import TrustResult


class EvidenceStoreHook:
    """Реализация AgentLifecycleHook, которая пишет каждое событие в
    EvidenceStore. Не требует знания о внутреннем устройстве вызывающей
    системы, только чтобы её три метода вызывали в подходящие моменты."""

    def __init__(self, store: EvidenceStore, collector: str = "prizolov_market", source: Optional[str] = None):
        self._store = store
        self._collector = collector
        self._source = source
        self._last_genome_hash: dict = {}

    def on_genome_extracted(self, agent_id: str, genome_hash: str) -> None:
        """Запоминает хэш генома для этого agent_id, чтобы приложить его
        к следующей записи on_trust_scored(). Сам геном не хранится
        здесь целиком, только его хэш (как и везде в проекте,
        см. GenomeLedger)."""
        self._last_genome_hash[agent_id] = genome_hash

    def on_trust_scored(self, agent_id: str, result: TrustResult, genome_hash: Optional[str] = None) -> int:
        """Пишет наблюдение в EvidenceStore. Возвращает id записи.

        genome_hash можно передать явно, если он у вас уже есть на
        момент вызова, это надёжнее, чем полагаться на транзиентный
        кэш из on_genome_extracted(): если процесс перезапустится между
        двумя вызовами, кэш обнулится, и связь Genome -> Trust Observation
        потеряется. Честная находка внешнего разбора, тот же класс
        бага, что был найден и исправлен в full_pipeline.py для истории
        predictability. Если genome_hash не передан, используется
        последнее значение из on_genome_extracted() в этом же процессе
        (обратная совместимость)."""
        resolved_hash = genome_hash if genome_hash is not None else self._last_genome_hash.get(agent_id)
        return self._store.record_observation(
            agent_id=agent_id,
            declared_score=result.score,
            declared_label=result.label,
            declared_confidence=result.confidence,
            genome_hash=resolved_hash,
            collector=self._collector,
            source=self._source,
            timestamp=datetime.now(timezone.utc),
        )

    def on_drift_alert(self, agent_id: str, report: DriftReportV2, genome_hash: Optional[str] = None) -> int:
        """Пишет наблюдение с прикреплённым инцидентом уровня SEVERE,
        если severity критичный ('severe' или 'sudden'), иначе MODERATE.
        Возвращает id записи.

        genome_hash: см. пояснение в on_trust_scored() выше, тот же
        принцип."""
        severity = (
            IncidentSeverity.SEVERE if report.severity in ("severe", "sudden")
            else IncidentSeverity.MODERATE
        )
        incident = Incident(
            description=f"Drift alert: {report.detail}"[:300],
            severity=severity,
            category=IncidentCategory.OTHER,
            source=IncidentSource.AUTOMATED_MONITOR,
            confirmed=True,
        )
        # report.ewma может быть None при недостаточных данных (severity
        # "insufficient_data") - на практике сюда не должны попадать такие
        # отчёты (alert=False для insufficient_data), но проверяем явно,
        # чтобы не записать в EvidenceStore нечисловой declared_score.
        declared_score = report.ewma if report.ewma is not None else 0.0
        resolved_hash = genome_hash if genome_hash is not None else self._last_genome_hash.get(agent_id)
        return self._store.record_observation(
            agent_id=agent_id,
            declared_score=declared_score,
            declared_label="Conditional" if severity == IncidentSeverity.MODERATE else "High Risk",
            declared_confidence="Low",
            genome_hash=resolved_hash,
            collector=self._collector,
            source=self._source,
            incidents=[incident],
            timestamp=datetime.now(timezone.utc),
        )
