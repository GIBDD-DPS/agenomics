"""
Agenomics — Genetics for AI Agents.

Оценка предсказуемости и совместимости личности ИИ-агентов
на основе методологии Agenomics (развитие Agent Genome Mapping™).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.0
"""

from .trust_score import (
    AgentGenome, TrustScorer, TrustResult, ImpactTier, Autonomy,
    DEFAULT_TRUST_WEIGHTS, TRUST_WEIGHT_PROFILES, AGENOMICS_ATTRIBUTION,
)
from .compatibility import (
    CompatibilityScorer, PairCompatibilityResult, TeamCompatibilityResult,
    DEFAULT_COMPAT_WEIGHTS, COMPAT_WEIGHT_PROFILES,
)
from .drift import DriftMonitor, DriftReport, ScoreSnapshot
from .feedback import IncidentFeedback, Incident, IncidentSeverity, ObservedScoreResult
from .ledger import GenomeLedger, LedgerEntry
from .matchmaker import GenomeMatchmaker, MatchResult
from .chain import ChainRiskAggregator, ChainRiskResult
from .extractor import PromptToGenomeExtractor, ExtractionError
from .reports import trust_report, compatibility_report

__all__ = [
    "AgentGenome", "TrustScorer", "TrustResult", "ImpactTier", "Autonomy",
    "DEFAULT_TRUST_WEIGHTS", "TRUST_WEIGHT_PROFILES", "AGENOMICS_ATTRIBUTION",
    "CompatibilityScorer", "PairCompatibilityResult", "TeamCompatibilityResult",
    "DEFAULT_COMPAT_WEIGHTS", "COMPAT_WEIGHT_PROFILES",
    "DriftMonitor", "DriftReport", "ScoreSnapshot",
    "IncidentFeedback", "Incident", "IncidentSeverity", "ObservedScoreResult",
    "GenomeLedger", "LedgerEntry",
    "GenomeMatchmaker", "MatchResult",
    "ChainRiskAggregator", "ChainRiskResult",
    "PromptToGenomeExtractor", "ExtractionError",
    "trust_report", "compatibility_report",
]

__version__ = "0.4.0"
