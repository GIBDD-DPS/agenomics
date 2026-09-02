"""
Agenomics — Genetics for AI Agents.

Оценка предсказуемости и совместимости личности ИИ-агентов
на основе методологии Agenomics (развитие Agent Genome Mapping™).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.2.0
"""

from .trust_score import AgentGenome, TrustScorer, TrustResult, ImpactTier, Autonomy
from .compatibility import CompatibilityScorer, PairCompatibilityResult, TeamCompatibilityResult

__all__ = [
    "AgentGenome", "TrustScorer", "TrustResult", "ImpactTier", "Autonomy",
    "CompatibilityScorer", "PairCompatibilityResult", "TeamCompatibilityResult",
]

__version__ = "0.2.0"
