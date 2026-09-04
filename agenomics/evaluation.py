"""
evaluation.py — Real-World Evaluation Layer (v0.6.0, обновлено в v0.7.0).

Автор: Dm.Andreyanov
Проект: Prizolov Lab

До этого модуля компоненты уровня Observed Behaviour существовали по
отдельности: IncidentFeedback пересчитывал score по инцидентам разово,
GenomeLedger вёл хэш-цепочку записей, DriftMonitor следил за трендом —
но не было единой точки сбора, которая связывала бы Declared Score,
реальные инциденты и дрейф ВО ВРЕМЕНИ для одного агента, чтобы затем
посчитать связь между ними.

RealWorldEvaluationLayer — эта единая точка. Она делает измерение
Incident Correlation принципиально ВОЗМОЖНЫМ, когда появятся реальные
production-данные — до сих пор такой инфраструктуры не было вообще,
только заглушка not_computable в benchmark/metrics.py.

[v0.7.0] Добавлен record_raw_observation() — низкоуровневый метод записи
по сырым score/label/confidence, без полноценного TrustResult. Нужен для
воспроизведения наблюдений, загруженных из agenomics.evidence.EvidenceStore
(персистентное хранилище — само по себе эта in-memory реализация
по-прежнему не переживает перезапуск процесса).

ВАЖНО: сама по себе эта инфраструктура не производит "валидацию" —
она лишь умеет корректно посчитать корреляцию, КОГДА вы передадите ей
реальные наблюдения. На синтетических/тестовых данных её тесты
проверяют только МЕХАНИКУ (правильность подсчёта), а не реальную
предсказательную силу методологии — то же разграничение, что и во
всём остальном проекте (см. benchmark/README.md).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .drift import DriftMonitorV2
from .feedback import Incident, IncidentSeverity
from .trust_score import TrustResult

_MIN_OBSERVATIONS_FOR_CORRELATION = 10  # произвольный, но явный и настраиваемый порог

_SEVERITY_WEIGHT = {
    IncidentSeverity.MINOR: 1,
    IncidentSeverity.MODERATE: 3,
    IncidentSeverity.SEVERE: 10,
}


def _pearson(xs: List[float], ys: List[float]) -> float:
    """Дублирует _pearson_correlation из benchmark/metrics.py намеренно:
    agenomics (ядро) не должен зависеть от benchmark/ (инструмент репо),
    зависимость должна идти только в одну сторону."""
    n = len(xs)
    if n == 0:
        return 0.0
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = (var_x * var_y) ** 0.5
    return cov / denom if denom else 0.0


@dataclass
class Observation:
    timestamp: datetime
    declared_score: float
    declared_label: str
    incidents: List[Incident] = field(default_factory=list)


@dataclass
class TrustRealityReport:
    agent_id: str
    status: str  # "insufficient_data" | "computed"
    n_observations: int
    correlation: Optional[float] = None
    declared_score_trend: Optional[str] = None  # severity из DriftMonitorV2
    incident_rate: Optional[float] = None  # средняя "нагрузка" инцидентов на наблюдение
    detail: str = ""


class RealWorldEvaluationLayer:
    """
    Собирает Declared Score + реальные инциденты + дрейф для агента во
    времени. Не база данных — in-memory, как и остальные компоненты
    уровня Observed Behaviour (docs/SPECIFICATION.md, раздел 8).
    """

    def __init__(self, min_observations: int = _MIN_OBSERVATIONS_FOR_CORRELATION):
        self._observations: Dict[str, List[Observation]] = {}
        self._drift = DriftMonitorV2()
        self._min_observations = min_observations

    def record_raw_observation(
        self,
        agent_id: str,
        score: float,
        label: str,
        confidence: str = "High",
        incidents: Optional[List[Incident]] = None,
        timestamp: Optional[datetime] = None,
    ) -> Observation:
        """
        Низкоуровневая запись — принимает сырые score/label/confidence,
        а не полноценный TrustResult. Нужна для двух случаев:
          1. record_observation() ниже — обычный путь через TrustResult;
          2. воспроизведение наблюдений из EvidenceStore (agenomics/evidence.py),
             где TrustResult не хранится целиком — только его ключевые поля.
        """
        ts = timestamp or datetime.now(timezone.utc)
        obs = Observation(
            timestamp=ts, declared_score=score, declared_label=label,
            incidents=list(incidents or []),
        )
        self._observations.setdefault(agent_id, []).append(obs)
        self._drift.record(agent_id, score, confidence, ts)
        return obs

    def record_observation(
        self,
        agent_id: str,
        declared_result: TrustResult,
        incidents: Optional[List[Incident]] = None,
        timestamp: Optional[datetime] = None,
    ) -> Observation:
        return self.record_raw_observation(
            agent_id, declared_result.score, declared_result.label,
            declared_result.confidence, incidents, timestamp,
        )

    def observations(self, agent_id: str) -> List[Observation]:
        return list(self._observations.get(agent_id, []))

    def trust_reality_report(self, agent_id: str) -> TrustRealityReport:
        """
        Считает РЕАЛЬНУЮ корреляцию между Declared Score и "нагрузкой"
        инцидентов на тех же наблюдениях — при условии достаточного
        количества данных. До этого — честный insufficient_data, а не
        подогнанное число на 2-3 точках.
        """
        obs_list = self._observations.get(agent_id, [])
        n = len(obs_list)

        if n < self._min_observations:
            return TrustRealityReport(
                agent_id=agent_id, status="insufficient_data", n_observations=n,
                detail=(
                    f"Нужно минимум {self._min_observations} наблюдений для "
                    f"содержательной корреляции, есть {n}. Это НЕ ошибка — "
                    f"реальная оценка предсказательной силы Trust Score "
                    f"физически требует времени эксплуатации в проде."
                ),
            )

        scores = [obs.declared_score for obs in obs_list]
        incident_loads = [
            sum(_SEVERITY_WEIGHT[i.severity] for i in obs.incidents) for obs in obs_list
        ]
        total_incidents = sum(len(obs.incidents) for obs in obs_list)

        correlation = _pearson(scores, incident_loads)
        incident_rate = total_incidents / n
        drift_report = self._drift.report(agent_id)

        return TrustRealityReport(
            agent_id=agent_id, status="computed", n_observations=n,
            correlation=round(correlation, 4),
            declared_score_trend=drift_report.severity,
            incident_rate=round(incident_rate, 3),
            detail=(
                f"Корреляция Пирсона между Declared Score и нагрузкой инцидентов "
                f"на {n} наблюдениях: {correlation:.4f}. Ожидается ОТРИЦАТЕЛЬНАЯ "
                f"корреляция, если методология действительно предсказательна "
                f"(выше score -> меньше инцидентов). Это первая версия Incident "
                f"Correlation, которая физически МОЖЕТ дать реальное число — "
                f"но только если сюда переданы настоящие production-наблюдения, "
                f"а не тестовые данные."
            ),
        )
