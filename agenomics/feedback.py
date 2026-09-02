"""
feedback.py — Incident Feedback Loop методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.0

Пересчитывает декларативный (self-reported) Trust Score в "наблюдаемый"
(Observed Trust Score) с учётом реальных подтверждённых инцидентов —
вместо статичной одноразовой оценки.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .trust_score import TrustScorer


class IncidentSeverity(str, Enum):
    MINOR = "minor"        # раздражает, но не опасно
    MODERATE = "moderate"  # реальная проблема без серьёзного ущерба
    SEVERE = "severe"      # утечка данных, неверное финансовое решение и т.п.


_SEVERITY_PENALTY = {
    IncidentSeverity.MINOR: 3.0,
    IncidentSeverity.MODERATE: 10.0,
    IncidentSeverity.SEVERE: 25.0,
}

_MAX_TOTAL_PENALTY = 60.0  # инциденты не должны обнулять score полностью


@dataclass
class Incident:
    description: str
    severity: IncidentSeverity
    axis: Optional[str] = None  # какая ось Trust Score пострадала, если известно


@dataclass
class ObservedScoreResult:
    declared_score: float
    observed_score: float
    total_penalty: float
    incidents: List[Incident] = field(default_factory=list)
    declared_label: str = ""
    observed_label: str = ""
    label_changed: bool = False


class IncidentFeedback:
    """Применяет реальные инциденты к декларативному Trust Score."""

    def apply(self, declared_score: float, declared_label: str, incidents: List[Incident]) -> ObservedScoreResult:
        total_penalty = sum(_SEVERITY_PENALTY[i.severity] for i in incidents)
        total_penalty = min(total_penalty, _MAX_TOTAL_PENALTY)
        observed = max(0.0, declared_score - total_penalty)

        # Переиспользуем ту же шкалу меток, что и TrustScorer, чтобы не
        # разъезжались пороги Trusted/Conditional/High Risk между модулями.
        observed_label = TrustScorer._label(observed)

        return ObservedScoreResult(
            declared_score=declared_score,
            observed_score=round(observed, 1),
            total_penalty=round(total_penalty, 1),
            incidents=list(incidents),
            declared_label=declared_label,
            observed_label=observed_label,
            label_changed=(observed_label != declared_label),
        )
