# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
accumulation.py. Scorecard накопления доказательств, v0.9.6.

Показывает, сколько данных уже собрано и сколько не хватает до
ориентиров накопления. Ориентиры операционные: они говорят, когда имеет
смысл снова смотреть на стабильность метрик, и НЕ являются требованиями
статистической мощности. Что можно утверждать на имеющихся данных,
решает уровень утверждений в Validation Engine (validation.py,
PROTOCOL_THRESHOLDS), а не этот модуль.

    agenomics scorecard frameworks_evidence.db --trust-model-version 0.9.6

[Unreleased] Scorecard строится по одной когорте (cohort_type, по
умолчанию natural): ориентиры для обычных и стресс-прогонов разные по
смыслу, и складывать их нельзя. agenomics scorecard --cohort-type all
печатает по scorecard на каждую когорту в базе, а не их сумму.

Проект: Prizolov Lab
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .evidence_graph import COHORT_TYPES, DEFAULT_COHORT

ACCUMULATION_TARGETS = {
    "observations": 500,        # прогоны с предсказаниями
    "agents": 30,
    "configurations": 100,
    "independence_groups": 4,
    "evidence_q3": 300,
    "evidence_q4": 50,
    # [Unreleased] 25 вместо 20: при holdout 40% это около 10 событий в
    # проверочной части, с запасом над порогом протокола в 5.
    "events_per_target": 25,    # событий на каждую основную цель
}

_LABELS = {
    "observations": "прогоны с предсказаниями",
    "agents": "агенты",
    "configurations": "конфигурации",
    "independence_groups": "группы независимости",
    "evidence_q3": "доказательства Q3",
    "evidence_q4": "доказательства и исходы Q4",
}


@dataclass
class ScorecardRow:
    metric: str
    label: str
    current: int
    target: int
    status: str  # "reached" | "in_progress"


def cohorts_in_store(store) -> List[str]:
    """Типы когорт, у которых в базе есть предсказания, в порядке COHORT_TYPES."""
    present = {r[0] or DEFAULT_COHORT for r in store._conn.execute("SELECT DISTINCT cohort_type FROM predictions")}
    return [c for c in COHORT_TYPES if c in present]


def accumulation_scorecard(store, trust_model_versions: Optional[Sequence[str]] = None,
                           cohort_type: str = DEFAULT_COHORT) -> List[ScorecardRow]:
    """Строки scorecard одной когорты. С trust_model_versions считаются
    только прогоны этих версий модели доверия и их предсказания и
    доказательства."""
    from .validation import validate_all_targets

    if cohort_type not in COHORT_TYPES:
        raise ValueError(f"cohort_type должен быть одним из {COHORT_TYPES}, получено {cohort_type!r}")
    conn = store._conn
    # Наблюдение входит в когорту, если у него есть предсказание этой
    # когорты; предсказания без типа считаются natural.
    version_filter = (" AND o.id IN (SELECT observation_id FROM predictions "
                      f"WHERE COALESCE(cohort_type, '{DEFAULT_COHORT}') = ?)")
    params = [cohort_type]
    if trust_model_versions:
        version_filter += f" AND o.trust_model_version IN ({','.join('?' * len(trust_model_versions))})"
        params += list(trust_model_versions)
    prediction_filter = f" AND COALESCE(p.cohort_type, '{DEFAULT_COHORT}') = ?"
    n_obs, n_agents, n_genomes = conn.execute(
        "SELECT COUNT(DISTINCT p.observation_id), COUNT(DISTINCT p.agent_id), COUNT(DISTINCT o.genome_hash) "
        f"FROM predictions p JOIN observations o ON o.id = p.observation_id WHERE 1=1{version_filter}{prediction_filter}",
        params + [cohort_type],
    ).fetchone()
    evidence = dict(conn.execute(
        "SELECT e.quality_level, COUNT(*) FROM evidence e JOIN observations o ON o.id = e.observation_id "
        f"WHERE e.fingerprint IS NOT NULL{version_filter} GROUP BY e.quality_level", params,
    ).fetchall())
    # Q4 у исходов (внешнее подтверждение), не только у доказательств
    q4_outcomes = conn.execute(
        "SELECT COUNT(*) FROM outcomes x JOIN predictions p ON p.id = x.prediction_id "
        "JOIN observations o ON o.id = p.observation_id "
        f"WHERE x.quality_level = 'Q4' AND x.fingerprint IS NOT NULL{version_filter}{prediction_filter}",
        params + [cohort_type],
    ).fetchone()[0]
    groups = conn.execute(
        "SELECT COUNT(DISTINCT d.independence_group) FROM outcomes x JOIN donors d ON d.donor_id = x.donor_id "
        f"JOIN predictions p ON p.id = x.prediction_id JOIN observations o ON o.id = p.observation_id "
        f"WHERE 1=1{version_filter}{prediction_filter}", params + [cohort_type],
    ).fetchone()[0]
    current: Dict[str, int] = {
        "observations": n_obs, "agents": n_agents, "configurations": n_genomes,
        "independence_groups": groups, "evidence_q3": evidence.get("Q3", 0), "evidence_q4": evidence.get("Q4", 0) + q4_outcomes,
    }
    rows = [_row(metric, _LABELS[metric], value, ACCUMULATION_TARGETS[metric]) for metric, value in current.items()]
    reports = validate_all_targets(store, trust_model_versions=trust_model_versions, cohort_types=[cohort_type])
    for target, report in reports.items():
        if report.legacy_note:
            continue
        rows.append(_row(f"events:{target}", f"события {target}", report.n_positive,
                         ACCUMULATION_TARGETS["events_per_target"]))
    return rows


def _row(metric: str, label: str, current: int, target: int) -> ScorecardRow:
    return ScorecardRow(metric, label, int(current or 0), target, "reached" if (current or 0) >= target else "in_progress")


def scorecard_text(rows: List[ScorecardRow], trust_model_versions: Optional[Sequence[str]] = None,
                   cohort_type: str = DEFAULT_COHORT) -> str:
    cohort = ", ".join(trust_model_versions) if trust_model_versions else "все версии"
    width = max((len(r.label) for r in rows), default=10)
    lines = [f"Scorecard накопления доказательств (когорта: {cohort}; тип когорты: {cohort_type})"]
    for r in rows:
        mark = "✅" if r.status == "reached" else "…"
        lines.append(f"  {mark} {r.label:<{width}} {r.current:>6} / {r.target}")
    lines.append("  Ориентиры накопления данных, не требования статистической мощности. Что можно "
                 "утверждать, показывает уровень утверждений в agenomics validate.")
    return "\n".join(lines)
