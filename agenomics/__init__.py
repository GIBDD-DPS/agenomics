"""
Agenomics. Genetics for AI Agents.

Оценка предсказуемости и совместимости личности ИИ-агентов
на основе методологии Agenomics (развитие Agent Genome Mapping™).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.7.3

Формальная спецификация уровней конвейера (Genome → Genome Schema →
Phenotype → Trust Model → Compatibility Model → Drift Model →
Observed Behaviour → Evolution/Mutation): см. docs/SPECIFICATION.md.
Протокол хранения реальных наблюдений: см. docs/AEP-001.md.
"""

from .trust_score import (
    AgentGenome, TrustScorer, TrustResult, ImpactTier, Autonomy,
    DEFAULT_TRUST_WEIGHTS, TRUST_WEIGHT_PROFILES, AGENOMICS_ATTRIBUTION,
    HOW_TO_GUIDE, HOW_TO_GUIDE_TRANSLATIONS, SUPPORTED_LANGUAGES,
)
from .compatibility import (
    CompatibilityScorer, PairCompatibilityResult, TeamCompatibilityResult,
    DEFAULT_COMPAT_WEIGHTS, COMPAT_WEIGHT_PROFILES,
)
from .phenotype import Phenotype, compute_phenotype, describe_genome_schema, GENOME_SCHEMA, FieldSpec
from .drift import DriftMonitor, DriftReport, ScoreSnapshot, DriftMonitorV2, DriftReportV2
from .per_axis_drift import PerAxisDriftMonitor, BASELINE_VOLATILITY_BY_AXIS
from .feedback import (
    IncidentFeedback, Incident, IncidentSeverity, IncidentCategory, IncidentSource,
    ObservedScoreResult,
)
from .ledger import GenomeLedger, LedgerEntry
from .matchmaker import GenomeMatchmaker, MatchResult
from .chain import ChainRiskAggregator, ChainRiskResult
from .heatmap import CompatibilityMatrix, build_compatibility_matrix, render_heatmap_svg
from .extractor import PromptToGenomeExtractor, ExtractionError
from .evaluation import RealWorldEvaluationLayer, Observation, TrustRealityReport
from .evidence import EvidenceStore, StoredObservation, replay_into_evaluation_layer, AEP_SCHEMA_VERSION
from .reports import trust_report, compatibility_report, trust_report_docx

__all__ = [
    "AgentGenome", "TrustScorer", "TrustResult", "ImpactTier", "Autonomy",
    "DEFAULT_TRUST_WEIGHTS", "TRUST_WEIGHT_PROFILES", "AGENOMICS_ATTRIBUTION",
    "HOW_TO_GUIDE", "HOW_TO_GUIDE_TRANSLATIONS", "SUPPORTED_LANGUAGES",
    "CompatibilityScorer", "PairCompatibilityResult", "TeamCompatibilityResult",
    "DEFAULT_COMPAT_WEIGHTS", "COMPAT_WEIGHT_PROFILES",
    "Phenotype", "compute_phenotype", "describe_genome_schema", "GENOME_SCHEMA", "FieldSpec",
    "DriftMonitor", "DriftReport", "ScoreSnapshot", "DriftMonitorV2", "DriftReportV2",
    "PerAxisDriftMonitor", "BASELINE_VOLATILITY_BY_AXIS",
    "IncidentFeedback", "Incident", "IncidentSeverity", "IncidentCategory", "IncidentSource",
    "ObservedScoreResult",
    "GenomeLedger", "LedgerEntry",
    "GenomeMatchmaker", "MatchResult",
    "ChainRiskAggregator", "ChainRiskResult",
    "CompatibilityMatrix", "build_compatibility_matrix", "render_heatmap_svg",
    "PromptToGenomeExtractor", "ExtractionError",
    "RealWorldEvaluationLayer", "Observation", "TrustRealityReport",
    "EvidenceStore", "StoredObservation", "replay_into_evaluation_layer", "AEP_SCHEMA_VERSION",
    "trust_report", "compatibility_report", "trust_report_docx",
]

__version__ = "0.7.3"
