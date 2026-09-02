"""
Agenomics — Genetics for AI Agents.

Оценка предсказуемости и совместимости личности ИИ-агентов
на основе методологии Agenomics (развитие Agent Genome Mapping™).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.3.0
"""

from .trust_score import (
    AgentGenome, TrustScorer, TrustResult, ImpactTier, Autonomy,
    DEFAULT_TRUST_WEIGHTS, TRUST_WEIGHT_PROFILES, AGENOMICS_ATTRIBUTION,
)
from .compatibility import (
    CompatibilityScorer, PairCompatibilityResult, TeamCompatibilityResult,
    DEFAULT_COMPAT_WEIGHTS, COMPAT_WEIGHT_PROFILES,
)

__all__ = [
    "AgentGenome", "TrustScorer", "TrustResult", "ImpactTier", "Autonomy",
    "DEFAULT_TRUST_WEIGHTS", "TRUST_WEIGHT_PROFILES", "AGENOMICS_ATTRIBUTION",
    "CompatibilityScorer", "PairCompatibilityResult", "TeamCompatibilityResult",
    "DEFAULT_COMPAT_WEIGHTS", "COMPAT_WEIGHT_PROFILES",
]

__version__ = "0.3.0"
