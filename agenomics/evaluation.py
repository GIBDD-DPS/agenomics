"""
evaluation.py. Real-World Evaluation Layer.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.7.10

До этого модуля компоненты уровня Observed Behaviour существовали по
отдельности: IncidentFeedback пересчитывал score по инцидентам разово,
GenomeLedger вёл хэш-цепочку записей, DriftMonitor следил за трендом.
Не было единой точки сбора, которая связывала бы Declared Score,
реальные инциденты и дрейф во времени для одного агента, чтобы затем
посчитать связь между ними.

RealWorldEvaluationLayer это единая точка. Она делает измерение
Incident Correlation принципиально возможным, когда появятся реальные
production-данные. До этого модуля такой инфраструктуры не было вообще,
только заглушка not_computable в benchmark/metrics.py.

record_raw_observation(): низкоуровневый метод записи по сырым
score/label/confidence, без полноценного TrustResult. Нужен для
воспроизведения наблюдений, загруженных из agenomics.evidence.EvidenceStore
(персистентное хранилище, само по себе эта in-memory реализация
по-прежнему не переживает перезапуск процесса).

Важно: сама по себе эта инфраструктура не производит "валидацию". Она
лишь умеет корректно посчитать корреляцию, когда вы передадите ей
реальные наблюдения. На синтетических/тестовых данных её тесты
проверяют только механику (правильность подсчёта), а не реальную
предсказательную силу методологии, то же разграничение, что и во
всём остальном проекте (см. benchmark/README.md).

evidence_strength (v0.7.9): корреляция на 10 наблюдениях и на 1000
наблюдениях технически обе "computed", но это вводит в заблуждение о
реальной статистической силе результата. Многоуровневая метка честнее
бинарного insufficient_data/computed.
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


def _evidence_strength(n: int) -> str:
    """Многоуровневая честность вместо бинарного insufficient/computed.

    10 наблюдений технически достаточно, чтобы Pearson не упал с ошибкой
    деления на ноль, но называть это "computed" наравне с 1000
    наблюдениями вводит в заблуждение о реальной статистической силе
    результата. Пороги (10/50/200/1000) - экспертная эвристика, не
    результат формального power analysis, и это стоит явно проговорить
    в любом отчёте, где эта метка используется."""
    if n < _MIN_OBSERVATIONS_FOR_CORRELATION:
        return "insufficient"
    elif n < 50:
        return "exploratory"
    elif n < 200:
        return "preliminary"
    elif n < 1000:
        return "validation_candidate"
    else:
        return "strong"


@dataclass
class TrustRealityReport:
    agent_id: str
    status: str  # "insufficient_data" | "computed"
    n_observations: int
    correlation: Optional[float] = None
    declared_score_trend: Optional[str] = None  # severity из DriftMonitorV2
    incident_rate: Optional[float] = None  # средняя "нагрузка" инцидентов на наблюдение
    detail: str = ""
    evidence_strength: str = "insufficient"  # insufficient/exploratory/preliminary/validation_candidate/strong


class RealWorldEvaluationLayer:
    """
    Собирает Declared Score + реальные инциденты + дрейф для агента во
    времени. Не база данных, in-memory, как и остальные компоненты
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
        Низкоуровневая запись, принимает сырые score/label/confidence,
        а не полноценный TrustResult. Нужна для двух случаев:
          1. record_observation() ниже, обычный путь через TrustResult;
          2. воспроизведение наблюдений из EvidenceStore (agenomics/evidence.py),
             где TrustResult не хранится целиком, только его ключевые поля.
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
        инцидентов на тех же наблюдениях, при условии достаточного
        количества данных. До этого честный insufficient_data, а не
        подогнанное число на 2-3 точках.
        """
        obs_list = self._observations.get(agent_id, [])
        n = len(obs_list)

        if n < self._min_observations:
            return TrustRealityReport(
                agent_id=agent_id, status="insufficient_data", n_observations=n,
                evidence_strength=_evidence_strength(n),
                detail=(
                    f"Нужно минимум {self._min_observations} наблюдений для "
                    f"содержательной корреляции, есть {n}. Это не ошибка. "
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
        strength = _evidence_strength(n)

        _STRENGTH_CAVEAT = {
            "insufficient": (
                f"n={n}. Формально прошло ваш собственный min_observations "
                f"({self._min_observations}), но всё ещё ниже универсального "
                f"порога 'exploratory' (10), ниже которого корреляция особенно "
                f"нестабильна. Если вы намеренно понизили min_observations, "
                f"относитесь к этому числу с осторожностью."
            ),
            "exploratory": (
                f"n={n}, уровень 'exploratory'. Корреляция на таком объёме "
                f"крайне нестабильна, статистический шум обычно доминирует "
                f"над реальным сигналом. Не делайте выводов о предсказательности "
                f"формулы на этом этапе, только накапливайте данные дальше."
            ),
            "preliminary": (
                f"n={n}, уровень 'preliminary'. Больше сигнала, чем при "
                f"exploratory, но всё ещё далеко от статистически надёжного "
                f"вывода."
            ),
            "validation_candidate": (
                f"n={n}, уровень 'validation_candidate'. Достаточно для "
                f"осторожных предварительных выводов, но baseline-сравнение "
                f"и temporal holdout ещё не проводились."
            ),
            "strong": (
                f"n={n}, уровень 'strong'. Достаточный объём для содержательного "
                f"статистического вывода, при условии, что инциденты отражают "
                f"поведенческие, а не инфраструктурные проблемы."
            ),
        }

        return TrustRealityReport(
            agent_id=agent_id, status="computed", n_observations=n,
            correlation=round(correlation, 4),
            declared_score_trend=drift_report.severity,
            incident_rate=round(incident_rate, 3),
            evidence_strength=strength,
            detail=(
                f"Корреляция Пирсона между Declared Score и нагрузкой инцидентов "
                f"на {n} наблюдениях: {correlation:.4f}. Ожидается отрицательная "
                f"корреляция, если методология действительно предсказательна "
                f"(выше score, меньше инцидентов). {_STRENGTH_CAVEAT[strength]}"
            ),
        )
