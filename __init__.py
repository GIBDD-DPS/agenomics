"""
Agenomics — Genetics for AI Agents.

Оценка предсказуемости и совместимости личности ИИ-агентов
на основе методологии Agenomics (развитие Agent Genome Mapping™).
"""

from .trust_score import AgentGenome, TrustScorer, TrustResult, ImpactTier, Autonomy

__all__ = ["AgentGenome", "TrustScorer", "TrustResult", "ImpactTier", "Autonomy"]

__version__ = "0.1.0"
