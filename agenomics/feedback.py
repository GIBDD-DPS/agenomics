"""
feedback.py. Incident Feedback Loop методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.7.3

Пересчитывает декларативный (self-reported) Trust Score в "наблюдаемый"
(Observed Trust Score) с учётом реальных подтверждённых инцидентов,
вместо статичной одноразовой оценки.

Incident расширен структурированными полями протокола AEP-001
(docs/AEP-001.md): category, source, confirmed, resolution.
Все новые поля опциональны. Старый код с Incident(description, severity)
продолжает работать без изменений.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .trust_score import TrustScorer


class IncidentSeverity(str, Enum):
    MINOR = "minor"        # раздражает, но не опасно
    MODERATE = "moderate"  # реальная проблема без серьёзного ущерба
    SEVERE = "severe"      # утечка данных, неверное финансовое решение и т.п.


class IncidentCategory(str, Enum):
    """Структурированная категория инцидента (AEP-001). Предпочтительнее
    свободного текста в description: категория агрегируется и сравнивается
    между разными источниками данных, а свободный текст нет."""
    RESPONSE_QUALITY = "response_quality"
    SAFETY = "safety"
    DATA_LEAK = "data_leak"
    BIAS = "bias"
    HALLUCINATION = "hallucination"
    COMPLIANCE = "compliance"
    OTHER = "other"


class IncidentSource(str, Enum):
    """Откуда взят инцидент. Важно для оценки надёжности данных при
    агрегации из разных источников (AEP-001, Provenance)."""
    USER_REPORT = "user_report"
    AUTOMATED_MONITOR = "automated_monitor"
    MANUAL_REVIEW = "manual_review"
    SUPPORT_TICKET = "support_ticket"
    OTHER = "other"


_SEVERITY_PENALTY = {
    IncidentSeverity.MINOR: 3.0,
    IncidentSeverity.MODERATE: 10.0,
    IncidentSeverity.SEVERE: 25.0,
}

_MAX_TOTAL_PENALTY = 60.0  # инциденты не должны обнулять score полностью

_MAX_SAFE_DESCRIPTION_LENGTH = 200  # эвристика для предупреждения о возможном PII


@dataclass
class Incident:
    description: str
    severity: IncidentSeverity
    axis: Optional[str] = None  # какая ось Trust Score пострадала, если известно

    # Поля протокола AEP-001, все опциональны для обратной совместимости.
    category: Optional[IncidentCategory] = None
    source: Optional[IncidentSource] = None
    confirmed: bool = True  # подтверждён ли инцидент человеком (не просто авто-флаг)
    resolution: Optional[str] = None  # "fixed"/"false_positive"/"pending"/свободный текст

    def __post_init__(self):
        if len(self.description) > _MAX_SAFE_DESCRIPTION_LENGTH:
            import warnings
            warnings.warn(
                f"Incident.description длиннее {_MAX_SAFE_DESCRIPTION_LENGTH} символов. "
                f"AEP-001 (Privacy) рекомендует не хранить сырой пользовательский текст "
                f"в description. Используйте category для агрегации, а description "
                f"оставляйте коротким служебным резюме. См. docs/AEP-001.md, раздел Privacy.",
                UserWarning, stacklevel=2,
            )


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
