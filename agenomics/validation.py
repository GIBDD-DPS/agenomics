# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
validation.py. Validation Engine методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab

Отвечает на один вопрос: предсказывает ли Trust Score, замороженный до
выполнения задачи, то, что произошло после. Работает только на парах
Prediction -> Outcome из Evidence Graph (evidence_graph.py), то есть на
данных, где score по построению не мог зависеть от исхода.

Что считается:
- ROC-AUC (ранжирует ли низкий score рискованные прогоны выше), PR-AUC,
  Brier и калибровка. Риск = 100 - Trust Score. Для Brier и калибровки
  риск наивно переводится в вероятность p = риск / 100: Trust Score не
  калиброван как вероятность, и калибровка это показывает, а не прячет;
- доверительный интервал AUC кластерным bootstrap по агентам: прогоны
  одного агента не независимы, и bootstrap по наблюдениям дал бы
  слишком узкий интервал;
- temporal holdout: порог риска выбирается на ранних предсказаниях,
  метрики считаются только на поздних;
- baseline: константа (доля инцидентов в калибровочной части) и
  историческая частота инцидентов у этого же агента. Второй baseline
  главный: если score не лучше "этот агент обычно падает", он не
  добавляет информации сверх имени агента;
- уровень агента: ранговая корреляция среднего score агента с его
  частотой инцидентов.

Вердикт никогда не "validated": только insufficient_data,
no_evidence_of_signal, signal_not_better_than_baseline или
signal_beats_baseline. Последний означает "на этих данных score лучше
baseline", а не доказанную предсказательную валидность методологии.

Только stdlib.
"""

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .evaluation import _evidence_strength
from .evidence_graph import COHORT_TYPES, DEFAULT_COHORT

# Прогон, упавший из-за окружения, не проверяет поведение агента: агент
# не работал. Такие предсказания исключаются целиком, а не считаются
# "без инцидента" по остальным донорам.
DEFAULT_EXCLUDED_OUTCOME_TYPES = ("infrastructure_error",)

# [Unreleased] Когорты по умолчанию: только natural. Стресс-когорты и
# внешние исходы проверяются отдельно, смесь только явно ("all"), см.
# docs/specs/validation-data-acquisition-v1.md, раздел 3.
DEFAULT_COHORT_TYPES = (DEFAULT_COHORT,)
ALL_COHORTS = "all"

# [Unreleased] Цели, где два донора оценивают одно и то же событие, и их
# согласие имеет смысл. У security доноры смотрят на разное (паттерн
# секрета в логе и раскрытие канарейки), поэтому согласие не считается.
DONOR_AGREEMENT_TARGETS = ("task_failure",)

# [Unreleased] Правило вывода стресс-сценария из ротации (ТЗ
# validation-data-acquisition-v1, раздел 5.4): после min_runs прогонов
# сценария частота событий вне [low, high] значит, что сценарий не различает
# агентов. Решение только по общей частоте, не по связи со score.
SCENARIO_RETIREMENT = {"min_runs": 50, "low": 0.05, "high": 0.95}

# Цель, по которой оценивается стресс-сценарий: событие, ради которого он
# устроен (у stress_task это неверный ответ, у stress_runtime падение).
SCENARIO_TARGETS = {
    "stress_runtime": "runtime_failure",
    "stress_security": "security_incident",
    "stress_task": "task_failure",
}

# [v0.9.5] Цели, которые больше не создаются, но остаются в накопленных
# базах. Отчёт по ним строится (данные есть), но помечается и идёт после
# основных целей: общая цель "был ли инцидент" смешивает разные события и
# не сравнима с раздельными целями.
# [v0.9.6] Пороги docs/VALIDATION_PROTOCOL.md, раздел 6: единственный
# источник чисел для вердикта и уровня утверждений.
PROTOCOL_THRESHOLDS = {
    "min_test_pairs": 30,         # пар в проверочной части для любого вердикта кроме insufficient_data
    "min_class_count": 5,         # событий и не-событий в проверочной части
    "preliminary_events": 20,     # событий цели для предварительного результата
    "preliminary_agents": 20,     # агентов для предварительного результата
    "min_groups": 2,              # групп независимости для предварительного результата
    "external_requires_q4": True,  # внешняя валидность только с исходами Q4 или подтверждёнными человеком
}

CLAIM_LEVELS = ("exploratory", "diagnostic", "preliminary", "external")
QUALITY_ORDER = ("Q0", "Q1", "Q2", "Q3", "Q4")

LEGACY_TARGETS = {
    "incident_in_run": "общая цель до v0.9.2; с v0.9.2 вместо неё runtime_failure, "
                       "security_incident и task_failure, новые предсказания под неё не создаются",
}

VERDICTS = (
    "insufficient_data",
    "no_evidence_of_signal",
    "signal_not_better_than_baseline",
    "signal_beats_baseline",
)


@dataclass
class ValidationPair:
    prediction_id: int
    agent_id: str
    trust_score: float
    occurred: bool
    frozen_at: datetime
    genome_hash: Optional[str] = None
    donor_ids: Tuple[str, ...] = ()           # доноры исходов, вошедших в пару
    independence_groups: Tuple[str, ...] = ()
    verified: bool = False                    # хотя бы один исход human/ground_truth
    max_quality: Optional[str] = None         # [v0.9.6] лучший уровень качества исходов пары
    cohort_type: str = DEFAULT_COHORT         # [Unreleased]
    model_version: Optional[str] = None       # [Unreleased] из снимка: модель прогона
    task_version: Optional[str] = None        # [Unreleased] из снимка: условие (когорта/задача/сценарий)
    group_outcomes: Dict[str, bool] = field(default_factory=dict)  # [Unreleased] исход по каждой группе

    @property
    def risk(self) -> float:
        return 100.0 - self.trust_score


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    n: int
    mean_predicted: float
    observed_rate: float


@dataclass
class Metrics:
    n: int
    n_positive: int
    roc_auc: Optional[float]
    pr_auc: Optional[float]
    brier: Optional[float]
    base_rate: Optional[float]


@dataclass
class HoldoutResult:
    calibration_n: int
    test_n: int
    split_at: Optional[str]
    trust_score: Metrics
    roc_auc_ci: Optional[Tuple[float, float]]
    auc_difference_vs_agent_history_ci: Optional[Tuple[float, float]]
    bootstrap_unit: str
    risk_threshold: Optional[float]
    precision: Optional[float]
    recall: Optional[float]
    f1: Optional[float]
    accuracy: Optional[float]
    baseline_majority_accuracy: Optional[float]
    baseline_constant_brier: Optional[float]
    baseline_agent_history: Metrics
    # [v0.9.6] Тот же интервал AUC, но ресэмплируются конфигурации (genome_hash):
    # сто прогонов одной конфигурации не сто независимых доказательств.
    roc_auc_ci_by_genome: Optional[Tuple[float, float]] = None


@dataclass
class ValidationReport:
    verdict: str
    detail: str
    n_pairs: int
    n_positive: int
    n_agents: int
    n_configurations: int
    evidence_strength: str
    filters: Dict
    overall: Metrics
    # [v0.9.2] Независимость: сколько доноров и групп независимости дали
    # исходы, вошедшие в пары, и сколько пар подтверждены человеком или
    # реальным исходом. n_rejected_outcomes: исходы, наблюдённые раньше
    # заморозки предсказания, отброшены повторной проверкой.
    n_donors: int = 0
    n_independence_groups: int = 0
    independence_groups: List[str] = field(default_factory=list)
    n_verified_pairs: int = 0
    n_rejected_outcomes: int = 0
    calibration: List[CalibrationBin] = field(default_factory=list)
    expected_calibration_error: Optional[float] = None
    agent_level_spearman: Optional[float] = None
    holdout: Optional[HoldoutResult] = None
    # [v0.9.5] Пояснение, если цель устаревшая (LEGACY_TARGETS), иначе None.
    legacy_note: Optional[str] = None
    # [v0.9.6] Независимость: сколько пар опираются на исход каждой группы,
    # доля крупнейшей группы, предупреждение.
    outcomes_per_group: Dict[str, int] = field(default_factory=dict)
    max_group_share: Optional[float] = None
    independence_warning: Optional[str] = None
    # [v0.9.6] Что эти данные позволяют утверждать (VALIDATION_PROTOCOL.md,
    # раздел 6) и что мешает следующему уровню. Отдельно от вердикта:
    # вердикт отвечает, есть ли сигнал, уровень, можно ли это заявлять.
    claim_level: str = "exploratory"
    claim_blockers: List[str] = field(default_factory=list)
    n_q4_pairs: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    # [Unreleased] Когорты в выборке и предупреждение, если они смешаны.
    cohort_types: List[str] = field(default_factory=list)
    cohort_warning: Optional[str] = None
    # [Unreleased] Согласие доноров (DONOR_AGREEMENT_TARGETS): сколько пар
    # оценили две и больше групп, сколько из них одинаково, и расхождения
    # вида "llm_judge=0,task_checker=1" -> число пар.
    donor_agreement: Optional[Dict] = None
    # [Unreleased] Пары и события по условию (task_version) и по модели:
    # условия не должны смешиваться незаметно.
    by_condition: Dict[str, Dict] = field(default_factory=dict)
    by_model: Dict[str, Dict] = field(default_factory=dict)


# --- Сборка пар ------------------------------------------------------------

def _parse_time(value: str) -> datetime:
    ts = datetime.fromisoformat(value)
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def _collect_pairs(
    store,
    target: Optional[str],
    outcome_types: Optional[Sequence[str]],
    exclude_outcome_types: Sequence[str],
    independence_groups: Optional[Sequence[str]],
    verification: Optional[Sequence[str]],
    agent_id: Optional[str],
    trust_model_versions: Optional[Sequence[str]] = None,
    min_quality: Optional[str] = None,
    cohort_types: Optional[Sequence[str]] = DEFAULT_COHORT_TYPES,
    since: Optional[datetime] = None,
) -> Tuple[List[ValidationPair], int]:
    genome_by_obs, version_by_obs = {}, {}
    for obs_id, genome_hash, version in store._conn.execute(
        "SELECT id, genome_hash, trust_model_version FROM observations"
    ):
        genome_by_obs[obs_id], version_by_obs[obs_id] = genome_hash, version
    pairs: List[ValidationPair] = []
    n_rejected = 0
    for p in store.get_predictions(agent_id):
        if target is not None and p.target != target:
            continue
        # [v0.9.6] Когорта по версии модели доверия: база накопительная, и
        # прогоны разных версий Trust Score проверяются по отдельности.
        if trust_model_versions is not None and version_by_obs.get(p.observation_id) not in trust_model_versions:
            continue
        if cohort_types is not None and p.cohort_type not in cohort_types:
            continue
        frozen = _parse_time(p.frozen_at)
        if since is not None and frozen < since:
            continue
        # [v0.9.2] Повторная проверка порядка времени. record_outcome() уже
        # отклоняет исход не позже заморозки, но база могла быть
        # импортирована или исправлена вручную: проспективная проверка не
        # должна полагаться на то, что каждая запись прошла через API.
        outcomes = []
        for o in p.outcomes:
            if _parse_time(o.observed_at) < frozen:
                n_rejected += 1
            else:
                outcomes.append(o)
        if any(o.outcome_type in exclude_outcome_types and o.occurred for o in outcomes):
            continue
        matching = [
            o for o in outcomes
            if o.outcome_type not in exclude_outcome_types
            and (outcome_types is None or o.outcome_type in outcome_types)
            and (independence_groups is None or o.independence_group in independence_groups)
            and (verification is None or o.verification in verification)
            and (min_quality is None or (o.quality_level is not None
                                         and QUALITY_ORDER.index(o.quality_level) >= QUALITY_ORDER.index(min_quality)))
        ]
        if not matching:
            continue
        pairs.append(ValidationPair(
            prediction_id=p.id, agent_id=p.agent_id, trust_score=p.trust_score,
            occurred=any(o.occurred for o in matching), frozen_at=frozen,
            genome_hash=genome_by_obs.get(p.observation_id),
            donor_ids=tuple(sorted({o.donor_id for o in matching})),
            independence_groups=tuple(sorted({o.independence_group for o in matching})),
            verified=any(o.verification in ("human", "ground_truth") for o in matching),
            max_quality=max((o.quality_level for o in matching if o.quality_level), default=None,
                            key=QUALITY_ORDER.index),
            cohort_type=p.cohort_type,
            model_version=p.snapshot.get("model_version"),
            task_version=p.snapshot.get("task_version"),
            group_outcomes={g: any(o.occurred for o in matching if o.independence_group == g)
                            for g in sorted({o.independence_group for o in matching})},
        ))
    return pairs, n_rejected


def build_pairs(
    store,
    target: Optional[str] = None,
    outcome_types: Optional[Sequence[str]] = None,
    exclude_outcome_types: Sequence[str] = DEFAULT_EXCLUDED_OUTCOME_TYPES,
    independence_groups: Optional[Sequence[str]] = None,
    verification: Optional[Sequence[str]] = None,
    agent_id: Optional[str] = None,
    cohort_types: Optional[Sequence[str]] = DEFAULT_COHORT_TYPES,
) -> List[ValidationPair]:
    """Пары (замороженный score, произошло ли событие).

    Событие считается произошедшим, если хотя бы один подходящий под
    фильтры исход его подтвердил. Предсказание без подходящих исходов
    пропускается: исход неизвестен, это не "не произошло". Предсказание,
    у которого произошёл исход из exclude_outcome_types, пропускается
    целиком: прогон не состоялся. Исходы, наблюдённые раньше заморозки
    предсказания, отбрасываются (v0.9.2); равенство допускается, как и в
    record_outcome() для времени по умолчанию."""
    return _collect_pairs(store, target, outcome_types, exclude_outcome_types,
                          independence_groups, verification, agent_id,
                          cohort_types=_normalize_cohorts(cohort_types))[0]


def _normalize_cohorts(cohort_types) -> Optional[Tuple[str, ...]]:
    """None или "all" (в том числе в списке) значит все когорты; иначе
    кортеж известных типов из COHORT_TYPES."""
    if cohort_types is None:
        return None
    if isinstance(cohort_types, str):
        cohort_types = (cohort_types,)
    if ALL_COHORTS in cohort_types:
        return None
    unknown = [c for c in cohort_types if c not in COHORT_TYPES]
    if unknown:
        raise ValueError(f"неизвестные типы когорт {unknown}; допустимы {COHORT_TYPES} или {ALL_COHORTS!r}")
    return tuple(cohort_types)


def prediction_targets(store) -> List[str]:
    """Все цели предсказаний в базе: основные по алфавиту, затем устаревшие
    (LEGACY_TARGETS)."""
    targets = [r[0] for r in store._conn.execute("SELECT DISTINCT target FROM predictions ORDER BY target")]
    return [t for t in targets if t not in LEGACY_TARGETS] + [t for t in targets if t in LEGACY_TARGETS]


# --- Метрики -----------------------------------------------------------------

def _average_ranks(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def roc_auc(scores: Sequence[float], labels: Sequence[bool]) -> Optional[float]:
    """AUC через ранги (Mann-Whitney), ничьи дают 0.5. scores: чем больше,
    тем выше предсказанный риск. None, если есть только один класс."""
    n_pos = sum(1 for y in labels if y)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = _average_ranks(scores)
    rank_sum_pos = sum(r for r, y in zip(ranks, labels) if y)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def average_precision(scores: Sequence[float], labels: Sequence[bool]) -> Optional[float]:
    """PR-AUC как average precision; объекты с равным score идут одним
    порогом, а не в произвольном порядке."""
    n_pos = sum(1 for y in labels if y)
    if n_pos == 0:
        return None
    pairs = sorted(zip(scores, labels), key=lambda t: -t[0])
    ap, tp, seen, prev_recall, i = 0.0, 0, 0, 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            tp += pairs[j][1]
            seen += 1
            j += 1
        recall = tp / n_pos
        ap += (recall - prev_recall) * (tp / seen)
        prev_recall = recall
        i = j
    return ap


def brier(probabilities: Sequence[float], labels: Sequence[bool]) -> Optional[float]:
    if not labels:
        return None
    return sum((p - float(y)) ** 2 for p, y in zip(probabilities, labels)) / len(labels)


def calibration_table(probabilities: Sequence[float], labels: Sequence[bool], n_bins: int = 10):
    """Равные по ширине корзины; пустые не выводятся. ECE: средневзвешенная
    разница между предсказанной и наблюдённой частотой."""
    bins: Dict[int, List[Tuple[float, bool]]] = {}
    for p, y in zip(probabilities, labels):
        bins.setdefault(min(int(p * n_bins), n_bins - 1), []).append((p, y))
    table = []
    ece = 0.0
    for b in sorted(bins):
        items = bins[b]
        mean_p = sum(p for p, _ in items) / len(items)
        rate = sum(1 for _, y in items if y) / len(items)
        table.append(CalibrationBin(b / n_bins, (b + 1) / n_bins, len(items), round(mean_p, 4), round(rate, 4)))
        ece += len(items) / len(labels) * abs(rate - mean_p)
    return table, (round(ece, 4) if labels else None)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3:
        return None
    rx, ry = _average_ranks(xs), _average_ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy) ** 0.5


def _metrics(risks: Sequence[float], labels: Sequence[bool], probabilities: Optional[Sequence[float]] = None) -> Metrics:
    probabilities = probabilities if probabilities is not None else [r / 100.0 for r in risks]
    n_pos = sum(1 for y in labels if y)
    auc = roc_auc(risks, labels)
    ap = average_precision(risks, labels)
    b = brier(probabilities, labels)
    return Metrics(
        n=len(labels), n_positive=n_pos,
        roc_auc=None if auc is None else round(auc, 4),
        pr_auc=None if ap is None else round(ap, 4),
        brier=None if b is None else round(b, 4),
        base_rate=round(n_pos / len(labels), 4) if labels else None,
    )


def _cluster_bootstrap(items, cluster_key, statistic, n_resamples: int, seed: int):
    """Кластерный bootstrap: ресэмплируются кластеры целиком. Возвращает
    95% интервал статистики или None, если она не вычислима в большинстве
    ресэмплов (например, в них остаётся один класс)."""
    rng = random.Random(seed)
    clusters: Dict[str, list] = {}
    for item in items:
        clusters.setdefault(cluster_key(item), []).append(item)
    keys = list(clusters)
    values = []
    for _ in range(n_resamples):
        sample = [x for k in (rng.choice(keys) for _ in keys) for x in clusters[k]]
        value = statistic(sample)
        if value is not None:
            values.append(value)
    if len(values) < n_resamples * 0.5:
        return None
    values.sort()
    last = len(values) - 1
    return round(values[int(0.025 * last)], 4), round(values[int(0.975 * last)], 4)


def _has_both_classes(pairs: Sequence[ValidationPair], minimum: int = 2) -> bool:
    n_pos = sum(1 for p in pairs if p.occurred)
    return n_pos >= minimum and len(pairs) - n_pos >= minimum


def bootstrap_auc_ci(
    pairs: Sequence[ValidationPair],
    n_resamples: int = 1000,
    seed: int = 0,
    by_agent: bool = True,
    by: Optional[str] = None,
) -> Optional[Tuple[float, float]]:
    """95% интервал AUC. by_agent: ресэмплируются агенты целиком со всеми
    их прогонами (кластерный bootstrap), иначе отдельные наблюдения.
    [v0.9.6] by="agent" | "genome" | "observation" задаёт кластер явно
    (by_agent остаётся для совместимости); у пары без genome_hash
    кластером служит агент.
    None при меньше чем двух примерах любого класса: с одним примером
    каждый ресэмпл, где он есть, даёт вырожденный AUC, и интервал вроде
    (1.0, 1.0) только вводил бы в заблуждение."""
    if not _has_both_classes(pairs):
        return None
    by = by or ("agent" if by_agent else "observation")
    keys = {
        "agent": lambda p: p.agent_id,
        "genome": lambda p: p.genome_hash or f"agent:{p.agent_id}",
        "observation": lambda p: str(p.prediction_id),
    }
    if by not in keys:
        raise ValueError(f"by должен быть одним из {tuple(keys)}, получено {by!r}")
    return _cluster_bootstrap(
        pairs, keys[by],
        lambda sample: roc_auc([p.risk for p in sample], [p.occurred for p in sample]),
        n_resamples, seed,
    )


def bootstrap_auc_difference_ci(
    pairs: Sequence[ValidationPair],
    baseline_scores: Sequence[float],
    n_resamples: int = 1000,
    seed: int = 0,
    by_agent: bool = True,
) -> Optional[Tuple[float, float]]:
    """95% интервал разницы AUC(Trust Score) - AUC(baseline) на одних и тех
    же ресэмплах. Сравнение двух точечных AUC без неопределённости
    объявляло бы победу там, где разница в пределах шума."""
    if not _has_both_classes(pairs):
        return None

    def difference(sample):
        labels = [p.occurred for p, _ in sample]
        a = roc_auc([p.risk for p, _ in sample], labels)
        b = roc_auc([s for _, s in sample], labels)
        return None if a is None or b is None else a - b

    return _cluster_bootstrap(
        list(zip(pairs, baseline_scores)),
        (lambda x: x[0].agent_id) if by_agent else (lambda x: str(x[0].prediction_id)),
        difference, n_resamples, seed,
    )


# --- Holdout -----------------------------------------------------------------

def _best_threshold(pairs: Sequence[ValidationPair]) -> Optional[float]:
    """Порог риска с максимальной статистикой Юдена (TPR - FPR)."""
    n_pos = sum(p.occurred for p in pairs)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    best, best_j = None, -1.0
    for t in sorted({p.risk for p in pairs}):
        tpr = sum(1 for p in pairs if p.occurred and p.risk >= t) / n_pos
        fpr = sum(1 for p in pairs if not p.occurred and p.risk >= t) / n_neg
        if tpr - fpr > best_j:
            best, best_j = t, tpr - fpr
    return best


def _holdout(pairs: List[ValidationPair], calibration_fraction: float, min_agents_for_cluster: int) -> HoldoutResult:
    ordered = sorted(pairs, key=lambda p: p.frozen_at)
    cut = int(len(ordered) * calibration_fraction)
    calib, test = ordered[:cut], ordered[cut:]
    labels = [p.occurred for p in test]

    calib_rate = sum(p.occurred for p in calib) / len(calib) if calib else None
    per_agent: Dict[str, List[bool]] = {}
    for p in calib:
        per_agent.setdefault(p.agent_id, []).append(p.occurred)
    agent_rate = {a: sum(v) / len(v) for a, v in per_agent.items()}
    history_prob = [agent_rate.get(p.agent_id, calib_rate or 0.0) for p in test]

    threshold = _best_threshold(calib)
    precision = recall = f1 = accuracy = majority_acc = None
    if threshold is not None and test:
        predicted = [p.risk >= threshold for p in test]
        tp = sum(1 for pr, y in zip(predicted, labels) if pr and y)
        fp = sum(1 for pr, y in zip(predicted, labels) if pr and not y)
        fn = sum(1 for pr, y in zip(predicted, labels) if not pr and y)
        precision = round(tp / (tp + fp), 4) if tp + fp else None
        recall = round(tp / (tp + fn), 4) if tp + fn else None
        f1 = round(2 * precision * recall / (precision + recall), 4) if precision and recall else None
        accuracy = round(sum(1 for pr, y in zip(predicted, labels) if pr == y) / len(test), 4)
    if calib and test:
        majority = calib_rate >= 0.5
        majority_acc = round(sum(1 for y in labels if y == majority) / len(test), 4)

    n_agents = len({p.agent_id for p in test})
    by_agent = n_agents >= min_agents_for_cluster
    return HoldoutResult(
        calibration_n=len(calib),
        test_n=len(test),
        split_at=test[0].frozen_at.isoformat() if test else None,
        trust_score=_metrics([p.risk for p in test], labels),
        roc_auc_ci=bootstrap_auc_ci(test, by_agent=by_agent) if test else None,
        auc_difference_vs_agent_history_ci=(
            bootstrap_auc_difference_ci(test, history_prob, by_agent=by_agent) if test else None
        ),
        bootstrap_unit="agent" if by_agent else "observation",
        risk_threshold=threshold,
        precision=precision, recall=recall, f1=f1, accuracy=accuracy,
        baseline_majority_accuracy=majority_acc,
        baseline_constant_brier=(
            round(brier([calib_rate] * len(test), labels), 4) if calib_rate is not None and test else None
        ),
        baseline_agent_history=_metrics(history_prob, labels, probabilities=history_prob),
        roc_auc_ci_by_genome=bootstrap_auc_ci(test, by="genome") if test else None,
    )


# --- Главная функция ---------------------------------------------------------

def validate(
    store,
    target: Optional[str] = None,
    outcome_types: Optional[Sequence[str]] = None,
    exclude_outcome_types: Sequence[str] = DEFAULT_EXCLUDED_OUTCOME_TYPES,
    independence_groups: Optional[Sequence[str]] = None,
    verification: Optional[Sequence[str]] = None,
    agent_id: Optional[str] = None,
    trust_model_versions: Optional[Sequence[str]] = None,
    min_quality: Optional[str] = None,
    cohort_types: Optional[Sequence[str]] = DEFAULT_COHORT_TYPES,
    since: Optional[datetime] = None,
    calibration_fraction: float = 0.6,
    min_test_pairs: int = 30,
    min_class_count: int = 5,
    min_agents_for_cluster_bootstrap: int = 5,
    _with_claims: bool = True,
) -> ValidationReport:
    """Сопоставляет замороженные предсказания с исходами. См. docstring модуля."""
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("calibration_fraction должен быть в (0, 1)")
    cohort_types = _normalize_cohorts(cohort_types)
    since = _normalize_since(since)
    filters = {
        "target": target, "outcome_types": list(outcome_types) if outcome_types else None,
        "exclude_outcome_types": list(exclude_outcome_types),
        "independence_groups": list(independence_groups) if independence_groups else None,
        "verification": list(verification) if verification else None, "agent_id": agent_id,
        "trust_model_versions": list(trust_model_versions) if trust_model_versions else None,
        "min_quality": min_quality,
        "cohort_types": list(cohort_types) if cohort_types is not None else [ALL_COHORTS],
        "since": since.isoformat() if since else None,
    }
    if min_quality is not None and min_quality not in QUALITY_ORDER:
        raise ValueError(f"min_quality должен быть одним из {QUALITY_ORDER}, получено {min_quality!r}")
    if target is None:
        targets = prediction_targets(store)
        if len(targets) > 1:
            # Одна и та же оценка записана под каждую цель: объединение
            # целей засчитало бы каждый прогон несколько раз.
            raise ValueError(
                f"в базе несколько целей предсказаний {targets}: укажите target "
                f"или используйте validate_all_targets()"
            )
    pairs, n_rejected = _collect_pairs(
        store, target, outcome_types, exclude_outcome_types, independence_groups, verification, agent_id,
        trust_model_versions, min_quality, cohort_types, since,
    )
    labels = [p.occurred for p in pairs]
    risks = [p.risk for p in pairs]
    overall = _metrics(risks, labels)
    calibration, ece = calibration_table([r / 100.0 for r in risks], labels) if pairs else ([], None)

    per_agent: Dict[str, List[ValidationPair]] = {}
    for p in pairs:
        per_agent.setdefault(p.agent_id, []).append(p)
    agent_spearman = spearman(
        [sum(p.trust_score for p in v) / len(v) for v in per_agent.values()],
        [sum(p.occurred for p in v) / len(v) for v in per_agent.values()],
    )

    report = ValidationReport(
        verdict="insufficient_data", detail="", n_pairs=len(pairs), n_positive=overall.n_positive,
        n_agents=len(per_agent), n_configurations=len({p.genome_hash for p in pairs if p.genome_hash}),
        evidence_strength=_evidence_strength(len(pairs)), filters=filters, overall=overall,
        calibration=calibration, expected_calibration_error=ece,
        agent_level_spearman=None if agent_spearman is None else round(agent_spearman, 4),
        n_donors=len({d for p in pairs for d in p.donor_ids}),
        n_independence_groups=len({g for p in pairs for g in p.independence_groups}),
        independence_groups=sorted({g for p in pairs for g in p.independence_groups}),
        n_verified_pairs=sum(1 for p in pairs if p.verified),
        n_rejected_outcomes=n_rejected,
        legacy_note=LEGACY_TARGETS.get(target),
    )

    if pairs:
        report.holdout = _holdout(pairs, calibration_fraction, min_agents_for_cluster_bootstrap)
    report.verdict, report.detail = _verdict(report, min_test_pairs, min_class_count, risks)

    # [v0.9.6] Независимость и уровень утверждений
    per_group: Dict[str, int] = {}
    for p in pairs:
        for g in p.independence_groups:
            per_group[g] = per_group.get(g, 0) + 1
    report.outcomes_per_group = dict(sorted(per_group.items()))
    if pairs:
        # Доля крупнейшей группы среди всех связей «пара – группа»: пара,
        # подтверждённая двумя группами, учитывается в обеих.
        report.max_group_share = round(max(per_group.values()) / sum(per_group.values()), 4) if per_group else None
        report.period_start = min(p.frozen_at for p in pairs).isoformat()
        report.period_end = max(p.frozen_at for p in pairs).isoformat()
        if report.n_independence_groups < PROTOCOL_THRESHOLDS["min_groups"]:
            report.independence_warning = (
                f"все исходы из {report.n_independence_groups} групп(ы) независимости "
                f"(нужно не меньше {PROTOCOL_THRESHOLDS['min_groups']}): исходы подтверждают сами себя"
            )
        elif report.max_group_share is not None and report.max_group_share > 0.9:
            report.independence_warning = (
                f"одна группа независимости даёт {report.max_group_share:.0%} подтверждений"
            )
    report.n_q4_pairs = sum(1 for p in pairs if p.max_quality == "Q4")
    report.cohort_types = sorted({p.cohort_type for p in pairs})
    report.by_condition = condition_breakdown(pairs, "task_version")
    report.by_model = condition_breakdown(pairs, "model_version")
    if len(report.cohort_types) > 1:
        report.cohort_warning = (
            f"в выборке смешаны когорты {report.cohort_types}: вывод по протоколу делается по каждой отдельно"
        )
    if target in DONOR_AGREEMENT_TARGETS:
        report.donor_agreement = donor_agreement(pairs)
    if _with_claims:
        report.claim_level, report.claim_blockers = _claim_level(store, report, target, filters, calibration_fraction)
    return report


def _normalize_since(since) -> Optional[datetime]:
    """Дата или строка ISO; без часового пояса считается UTC."""
    if since is None or since == "":
        return None
    value = since if isinstance(since, datetime) else datetime.fromisoformat(str(since))
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def condition_breakdown(pairs: Sequence[ValidationPair], key: str) -> Dict[str, Dict]:
    """[Unreleased] Пары и события по значению поля пары (task_version или
    model_version); пары без значения идут под "—" (до снимков v0.9.6)."""
    out: Dict[str, Dict] = {}
    for p in pairs:
        row = out.setdefault(getattr(p, key) or "—", {"pairs": 0, "events": 0})
        row["pairs"] += 1
        row["events"] += int(p.occurred)
    for row in out.values():
        row["rate"] = round(row["events"] / row["pairs"], 4) if row["pairs"] else None
    return dict(sorted(out.items()))


def scenario_rule_status(pairs: int, events: int) -> str:
    """[Unreleased] Статус правила 5.4 для одного сценария."""
    r = SCENARIO_RETIREMENT
    if pairs < r["min_runs"]:
        return f"рано ({pairs} < {r['min_runs']})"
    rate = events / pairs
    return "различает" if r["low"] <= rate <= r["high"] else "заменить"


def donor_agreement(pairs: Sequence[ValidationPair]) -> Dict:
    """[Unreleased] Согласие групп независимости на парах, которые оценили
    две и больше групп. Расхождение говорит о проблеме одного из доноров
    и разбирается отдельно; голосованием доноров исход не сводится."""
    compared = [p for p in pairs if len(p.group_outcomes) >= 2]
    disagreements: Dict[str, int] = {}
    n_agree = 0
    for p in compared:
        if len(set(p.group_outcomes.values())) == 1:
            n_agree += 1
            continue
        key = ",".join(f"{g}={int(v)}" for g, v in sorted(p.group_outcomes.items()))
        disagreements[key] = disagreements.get(key, 0) + 1
    return {
        "n_compared": len(compared), "n_agree": n_agree,
        "agreement_rate": round(n_agree / len(compared), 4) if compared else None,
        "disagreements": dict(sorted(disagreements.items())),
    }


def validate_all_targets(store, **kwargs) -> Dict[str, "ValidationReport"]:
    """validate() отдельно для каждой цели предсказаний в базе."""
    kwargs.pop("target", None)
    return {target: validate(store, target=target, **kwargs) for target in prediction_targets(store)}


def _version_key(version: str):
    return tuple(int(x) if x.isdigit() else x for x in str(version).replace("-", ".").split("."))


def _previous_cohort(store, versions: Sequence[str]) -> Optional[str]:
    """Версия модели доверия, предшествующая единственной выбранной."""
    if not versions or len(versions) != 1:
        return None
    known = sorted(
        {r[0] for r in store._conn.execute(
            "SELECT DISTINCT o.trust_model_version FROM predictions p JOIN observations o ON o.id = p.observation_id "
            "WHERE o.trust_model_version IS NOT NULL")},
        key=_version_key,
    )
    earlier = [v for v in known if _version_key(v) < _version_key(versions[0])]
    return earlier[-1] if earlier else None


def _claim_level(store, report: ValidationReport, target, filters, calibration_fraction) -> Tuple[str, List[str]]:
    """Уровень утверждений по порогам протокола и список того, что мешает
    следующему уровню. Уровень повышается только по порядку."""
    t = PROTOCOL_THRESHOLDS
    if report.verdict == "insufficient_data":
        return "exploratory", [f"вердикт insufficient_data: {report.detail}"]

    blockers = []
    if report.n_positive < t["preliminary_events"]:
        blockers.append(f"событий {report.n_positive} < {t['preliminary_events']}")
    if report.n_agents < t["preliminary_agents"]:
        blockers.append(f"агентов {report.n_agents} < {t['preliminary_agents']}")
    if report.n_independence_groups < t["min_groups"]:
        blockers.append(f"групп независимости {report.n_independence_groups} < {t['min_groups']}")
    if report.verdict != "signal_beats_baseline":
        blockers.append(f"вердикт {report.verdict}, нужен signal_beats_baseline")
    previous = _previous_cohort(store, filters.get("trust_model_versions") or [])
    if previous is None:
        blockers.append("нет повторения на другой когорте (выберите одну версию: --trust-model-version)")
    else:
        kwargs = {k: v for k, v in filters.items() if k not in ("target", "trust_model_versions")}
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        earlier = validate(store, target=target, trust_model_versions=[previous],
                           calibration_fraction=calibration_fraction, _with_claims=False, **kwargs)
        if earlier.verdict != "signal_beats_baseline":
            blockers.append(f"на предыдущей когорте {previous} вердикт {earlier.verdict}")
    if blockers:
        return "diagnostic", blockers

    external_blockers = []
    if t["external_requires_q4"] and report.n_q4_pairs == 0 and report.n_verified_pairs == 0:
        external_blockers.append("Q4 = 0: нет исходов, подтверждённых внешней системой или человеком")
    if external_blockers:
        return "preliminary", external_blockers
    return "external", []


def _verdict(report: ValidationReport, min_test_pairs: int, min_class_count: int, risks: Sequence[float]):
    h = report.holdout
    if not report.n_pairs:
        return "insufficient_data", "Нет ни одной пары Prediction -> Outcome под эти фильтры."
    if len(set(risks)) == 1:
        return "insufficient_data", (
            f"Все {report.n_pairs} предсказаний имеют одинаковый Trust Score: ранжировать нечего. "
            f"Так бывает на первых прогонах, пока истории ещё нет."
        )
    test_pos = h.trust_score.n_positive
    test_neg = h.test_n - test_pos
    if h.test_n < min_test_pairs or test_pos < min_class_count or test_neg < min_class_count:
        return "insufficient_data", (
            f"В проверочной (поздней) части {h.test_n} пар, из них с событием {test_pos}, без события {test_neg}; "
            f"нужно минимум {min_test_pairs} пар и по {min_class_count} каждого класса."
        )
    auc = h.trust_score.roc_auc
    ci = h.roc_auc_ci
    ci_text = f"95% CI [{ci[0]}, {ci[1]}] ({h.bootstrap_unit} bootstrap)" if ci else "CI не вычислим"
    if ci is None or ci[0] <= 0.5:
        return "no_evidence_of_signal", (
            f"ROC-AUC на проверочной части {auc}, {ci_text}: интервал не исключает случайное угадывание."
        )
    baseline_auc = h.baseline_agent_history.roc_auc
    diff_ci = h.auc_difference_vs_agent_history_ci
    if baseline_auc is not None and (diff_ci is None or diff_ci[0] <= 0):
        diff_text = f"95% CI разницы [{diff_ci[0]}, {diff_ci[1]}]" if diff_ci else "CI разницы не вычислим"
        return "signal_not_better_than_baseline", (
            f"ROC-AUC {auc} ({ci_text}) против baseline 'историческая частота инцидентов агента' "
            f"{baseline_auc}, {diff_text}: превосходство над baseline не отличимо от шума, score не "
            f"добавляет доказанной информации сверх того, какой это агент."
        )
    diff_text = f", 95% CI разницы AUC [{diff_ci[0]}, {diff_ci[1]}]" if diff_ci else ""
    return "signal_beats_baseline", (
        f"ROC-AUC {auc} ({ci_text}) выше baseline 'историческая частота агента' ({baseline_auc}{diff_text}). "
        f"Это результат на этих данных и этом target, а не доказанная предсказательная валидность: "
        f"объём выборки '{report.evidence_strength}', агентов {report.n_agents}."
    )


_ERROR_CLASS = re.compile(r"error_class=([A-Za-z_]+)")


def cohort_summary(store, trust_model_versions: Optional[Sequence[str]] = None,
                   cohort_types: Optional[Sequence[str]] = DEFAULT_COHORT_TYPES, since=None) -> Dict:
    """[Unreleased] Объём той выборки, которую проверяет отчёт: те же когорта,
    версия модели доверия и период, что у validate(). Шапка отчёта раньше
    показывала всю базу, и отчёт стресс-когорты на 60 парах выглядел как
    построенный на тысячах наблюдений.

    Прогон исключён, если у его предсказаний есть исход infrastructure_error
    (сбой окружения или обвязки); класс берётся из details исхода."""
    cohort_types = _normalize_cohorts(cohort_types)
    since = _normalize_since(since)
    rows = store._conn.execute(
        "SELECT p.id, p.observation_id, p.agent_id, COALESCE(p.cohort_type, ?), p.frozen_at, "
        "o.genome_hash, o.trust_model_version FROM predictions p JOIN observations o ON o.id = p.observation_id",
        (DEFAULT_COHORT,),
    ).fetchall()
    selected = [
        r for r in rows
        if (cohort_types is None or r[3] in cohort_types)
        and (not trust_model_versions or r[6] in trust_model_versions)
        and (since is None or _parse_time(r[4]) >= since)
    ]
    pred_ids = [r[0] for r in selected]
    obs_ids = sorted({r[1] for r in selected})
    summary = {
        "runs": len(obs_ids), "predictions": len(pred_ids),
        "agents": len({r[2] for r in selected}), "configurations": len({r[5] for r in selected if r[5]}),
        "cohort_types": sorted({r[3] for r in selected}),
        "period_start": min((r[4] for r in selected), default=None),
        "period_end": max((r[4] for r in selected), default=None),
        "excluded_runs": 0, "excluded_by_class": {}, "evidence_by_quality": {}, "outcomes_by_quality": {},
        "q4_outcomes": 0,
    }
    if not pred_ids:
        return summary

    def chunks(values, size=500):
        for i in range(0, len(values), size):
            yield values[i:i + size]

    excluded: Dict[int, str] = {}
    by_quality: Dict[str, int] = {}
    for chunk in chunks(pred_ids):
        marks = ",".join("?" * len(chunk))
        for obs_id, outcome_type, occurred, details, quality in store._conn.execute(
            "SELECT p.observation_id, x.outcome_type, x.occurred, x.details, x.quality_level FROM outcomes x "
            f"JOIN predictions p ON p.id = x.prediction_id WHERE x.prediction_id IN ({marks})", chunk,
        ):
            if outcome_type == "infrastructure_error" and occurred:
                match = _ERROR_CLASS.search(details or "")
                excluded.setdefault(obs_id, match.group(1) if match else "unknown")
            if quality:
                by_quality[quality] = by_quality.get(quality, 0) + 1
    evidence: Dict[str, int] = {}
    for chunk in chunks(obs_ids):
        marks = ",".join("?" * len(chunk))
        for quality, n in store._conn.execute(
            f"SELECT quality_level, COUNT(*) FROM evidence WHERE observation_id IN ({marks}) GROUP BY quality_level", chunk,
        ):
            evidence[quality] = evidence.get(quality, 0) + n
    classes: Dict[str, int] = {}
    for error_class in excluded.values():
        classes[error_class] = classes.get(error_class, 0) + 1
    summary.update(
        excluded_runs=len(excluded), excluded_by_class=dict(sorted(classes.items(), key=lambda kv: -kv[1])),
        evidence_by_quality={q: evidence.get(q, 0) for q in QUALITY_ORDER},
        outcomes_by_quality={q: by_quality.get(q, 0) for q in QUALITY_ORDER},
        q4_outcomes=by_quality.get("Q4", 0),
    )
    return summary


def cohort_summary_text(summary: Dict, filters: Optional[Dict] = None) -> str:
    filters = filters or {}
    versions = ", ".join(filters.get("trust_model_versions") or []) or "все версии"
    since = f", с {filters['since']}" if filters.get("since") else ""
    excluded = ", ".join(f"{k} {v}" for k, v in summary["excluded_by_class"].items())
    lines = [
        f"Выборка отчёта (когорты {', '.join(summary['cohort_types']) or '—'}; trust_model_version {versions}{since}):",
        f"  прогонов {summary['runs']}, исключено как сбой окружения {summary['excluded_runs']}"
        + (f" ({excluded})" if excluded else "")
        + f", агентов {summary['agents']}, конфигураций {summary['configurations']}, предсказаний {summary['predictions']}",
        "  Доказательства: " + ", ".join(f"{q} {n}" for q, n in summary["evidence_by_quality"].items())
        + "; исходы: " + ", ".join(f"{q} {n}" for q, n in summary["outcomes_by_quality"].items()),
    ]
    return "\n".join(lines)


def evidence_profile_text(profile, reports: Optional[Dict[str, "ValidationReport"]] = None,
                          cohort: Optional[Dict] = None) -> str:
    """Шапка отчёта: объём и качество данных до вердиктов по целям. Без
    неё по отчёту не видно, на чём он построен.

    [v0.9.6] Уровни N раздельно: предсказания, наблюдения (прогоны) с
    предсказаниями, агенты, конфигурации. Одно наблюдение даёт по
    предсказанию на каждую цель, поэтому предсказаний больше, чем
    независимых прогонов. С reports добавляется число событий по целям."""
    quality = ", ".join(f"{level} {n}" for level, n in profile.evidence_by_quality.items())
    lines = [
        f"База: наблюдений {profile.n_observations}, агентов {profile.n_agents}, "
        f"genome_hash {profile.n_genomes} (включая хэши до v0.9.0, менявшиеся почти каждый прогон)",
        f"  С предсказаниями: наблюдений (прогонов) {profile.n_predicted_observations}, "
        f"агентов {profile.n_predicted_agents}, конфигураций {profile.n_predicted_genomes}; "
        f"предсказаний {profile.n_predictions} (по одному на цель), с исходом {profile.n_predictions_with_outcome}, "
        f"подтверждённых человеком/реальностью исходов {profile.n_verified_outcomes}",
        f"  Доказательств {profile.n_evidence} ({quality}), доноров {profile.n_donors}, "
        f"групп независимости {profile.n_independence_groups}",
        f"  Исходы по качеству: " + ", ".join(f"{q} {n}" for q, n in profile.outcomes_by_quality.items()),
    ]
    if reports:
        events = ", ".join(
            f"{target} {r.n_positive} из {r.n_pairs}" + (" (устаревшая)" if r.legacy_note else "")
            for target, r in reports.items()
        )
        lines.append(f"  Событий по целям (после исключения сбоев окружения): {events}")
        versions = next(iter(reports.values())).filters.get("trust_model_versions")
        if versions:
            lines.append(f"  Цели проверяются только по trust_model_version {', '.join(versions)}; "
                         f"строки выше описывают всю базу")
        cohorts = next(iter(reports.values())).filters.get("cohort_types")
        if cohorts:
            lines.append(f"  Когорты: {', '.join(cohorts)} (по умолчанию natural; --cohort-type выбирает другие)")
    if cohort is not None:
        # [Unreleased] Строки выше описывают всю базу; выборка отчёта отдельно.
        lines.append(cohort_summary_text(cohort, next(iter(reports.values())).filters if reports else None))
    return "\n".join(lines)


def validation_report_text(report: ValidationReport) -> str:
    o, h = report.overall, report.holdout
    target = report.filters.get("target")
    lines = [
        f"Validation Engine{f' [{target}]' if target else ''}: {report.verdict}"
        + (" (устаревшая цель)" if report.legacy_note else ""),
        f"  {report.detail}",
    ]
    if report.legacy_note:
        lines.append(f"  Устаревшая цель: {report.legacy_note}")
    lines += [
        f"  Пары: {report.n_pairs} (с событием {report.n_positive}), агентов {report.n_agents}, "
        f"конфигураций {report.n_configurations}, объём выборки '{report.evidence_strength}' "
        f"(только по числу пар; что можно утверждать, см. уровень утверждений)",
        f"  Независимость: доноров {report.n_donors}, групп {report.n_independence_groups} "
        f"{report.independence_groups}, подтверждённых человеком/реальностью пар {report.n_verified_pairs}"
        + (f", отброшено исходов раньше заморозки: {report.n_rejected_outcomes}" if report.n_rejected_outcomes else ""),
    ]
    if report.outcomes_per_group:
        lines.append(f"    Пар по группам: {report.outcomes_per_group}, доля крупнейшей {report.max_group_share}")
    if report.independence_warning:
        lines.append(f"    ⚠️ {report.independence_warning}")
    if report.donor_agreement and report.donor_agreement["n_compared"]:
        a = report.donor_agreement
        lines.append(f"    Согласие доноров: {a['n_agree']} из {a['n_compared']} ({a['agreement_rate']}), "
                     f"расхождения {a['disagreements'] or 'нет'}")
    if report.cohort_warning:
        lines.append(f"  ⚠️ {report.cohort_warning}")
    if len(report.by_condition) > 1 or (report.by_condition and "—" not in report.by_condition):
        cohorts = report.cohort_types
        scenario = len(cohorts) == 1 and SCENARIO_TARGETS.get(cohorts[0]) == target
        parts = [f"{name} {row['events']}/{row['pairs']}"
                 + (f" [{scenario_rule_status(row['pairs'], row['events'])}]" if scenario else "")
                 for name, row in report.by_condition.items()]
        lines.append("  По условиям (событий/пар): " + "; ".join(parts))
        lines.append("  По моделям: " + ", ".join(f"{m} {row['events']}/{row['pairs']}" for m, row in report.by_model.items()))
    lines += [
        f"  Вся выборка: ROC-AUC {o.roc_auc}, PR-AUC {o.pr_auc} (base rate {o.base_rate}), "
        f"Brier {o.brier}, ECE {report.expected_calibration_error}",
        f"  Уровень агента: Spearman(средний score, частота событий) = {report.agent_level_spearman}",
    ]
    if h:
        lines += [
            f"  Holdout: калибровка {h.calibration_n}, проверка {h.test_n} (с {h.split_at})",
            f"    Trust Score: ROC-AUC {h.trust_score.roc_auc} CI {h.roc_auc_ci} (bootstrap по {_UNIT[h.bootstrap_unit]}), "
            f"CI по конфигурациям {h.roc_auc_ci_by_genome}, PR-AUC {h.trust_score.pr_auc}, Brier {h.trust_score.brier}",
            f"    Порог риска {h.risk_threshold}: precision {h.precision}, recall {h.recall}, F1 {h.f1}, "
            f"accuracy {h.accuracy} (majority class {h.baseline_majority_accuracy})",
            f"    Baseline история агента: ROC-AUC {h.baseline_agent_history.roc_auc} "
            f"(CI разницы с Trust Score {h.auc_difference_vs_agent_history_ci}), "
            f"Brier {h.baseline_agent_history.brier}; константа: Brier {h.baseline_constant_brier}",
        ]
    lines.append(f"  Уровень утверждений: {report.claim_level}"
                 + (f"; до следующего не хватает: {'; '.join(report.claim_blockers)}" if report.claim_blockers else ""))
    lines.append("  Brier и калибровка считаются по наивной вероятности p = (100 - score) / 100.")
    return "\n".join(lines)


_UNIT = {"agent": "агентам", "observation": "прогонам", "genome": "конфигурациям"}


def _breakdown_markdown(report: ValidationReport, target: str) -> List[str]:
    """[Unreleased] Пары и события по условию и по модели; для цели, ради
    которой устроена стресс-когорта, ещё и статус правила 5.4 по сценарию."""
    if not report.by_condition:
        return []
    cohorts = report.cohort_types
    scenario = len(cohorts) == 1 and SCENARIO_TARGETS.get(cohorts[0]) == target
    head = "| Условие | Пар | Событий | Доля |" + (" Правило 5.4 |" if scenario else "")
    md = ["", "По условиям:", "", head, "|---|---:|---:|---:|" + ("---|" if scenario else "")]
    for name, row in report.by_condition.items():
        md.append(f"| {name} | {row['pairs']} | {row['events']} | {row['rate']} |"
                  + (f" {scenario_rule_status(row['pairs'], row['events'])} |" if scenario else ""))
    md += ["", "По моделям: " + ", ".join(f"{m} {row['events']}/{row['pairs']}" for m, row in report.by_model.items())]
    return md


def validation_report_markdown(profile, reports: Dict[str, "ValidationReport"], integrity: Optional[Dict] = None,
                               cohort: Optional[Dict] = None) -> str:
    """[v0.9.6] Полный отчёт для артефакта прогона: когорта, объём,
    доказательства, целостность, каждая цель с вердиктом и уровнем
    утверждений, устаревшие цели отдельно (ТЗ v0.9.6, п. 5.3)."""
    first = next(iter(reports.values()), None)
    filters = first.filters if first else {}
    starts = [r.period_start for r in reports.values() if r.period_start]
    ends = [r.period_end for r in reports.values() if r.period_end]
    md = [
        "# Agenomics Validation Report",
        "",
        "## Когорта",
        f"- trust_model_version: {', '.join(filters.get('trust_model_versions') or []) or 'все версии'}",
        f"- тип когорты: {', '.join(filters.get('cohort_types') or [DEFAULT_COHORT])}",
        f"- период: {min(starts) if starts else '—'} … {max(ends) if ends else '—'}",
        f"- фильтры: " + ", ".join(f"{k}={v}" for k, v in filters.items()
                                   if v and k not in ("target", "trust_model_versions", "cohort_types")),
        "",
    ]
    if cohort is not None:
        # [Unreleased] Объём именно этой выборки: когорта, версия, период.
        excluded = ", ".join(f"{k} {v}" for k, v in cohort["excluded_by_class"].items()) or "нет"
        md += [
            "## Объём выборки отчёта",
            f"- прогонов {cohort['runs']}, из них исключено как сбой окружения или обвязки "
            f"{cohort['excluded_runs']} ({excluded})",
            f"- агентов {cohort['agents']}, конфигураций {cohort['configurations']}, предсказаний {cohort['predictions']}",
            f"- период: {cohort['period_start'] or '—'} … {cohort['period_end'] or '—'}",
            "",
            "| Уровень | Доказательств | Исходов |", "|---|---:|---:|",
            *[f"| {q} | {cohort['evidence_by_quality'].get(q, 0)} | {cohort['outcomes_by_quality'].get(q, 0)} |"
              for q in QUALITY_ORDER],
            "",
            "## Q4: внешнее подтверждение",
            f"- исходов Q4 в выборке: {cohort['q4_outcomes']}"
            + ("" if cohort["q4_outcomes"] else
               ". Framework Evaluation Q4 не пишет: внешний источник исходов — prizolov-sports-ai, своя база "
               "(сводка и проверка Q4: GET /api/v1/admin/agenomics сервиса)"),
            "",
        ]
    md += [
        "## Вся база (для контекста)" if cohort is not None else "## Объём",
        f"- наблюдений в базе: {profile.n_observations}, агентов {profile.n_agents}",
        f"- с предсказаниями: прогонов {profile.n_predicted_observations}, агентов {profile.n_predicted_agents}, "
        f"конфигураций {profile.n_predicted_genomes}, предсказаний {profile.n_predictions}",
        f"- повторы, не вошедшие в счёт: доказательств {profile.n_duplicate_evidence}, исходов "
        f"{profile.n_duplicate_outcomes}, предсказаний {profile.n_duplicate_predictions}; исходов без класса "
        f"{profile.n_outcomes_without_class}",
        "",
        "## Доказательства",
        "| Уровень | Доказательств | Исходов |", "|---|---:|---:|",
        *[f"| {q} | {n} | {profile.outcomes_by_quality.get(q, 0)} |" for q, n in profile.evidence_by_quality.items()],
        "",
        f"Группы независимости ({profile.n_independence_groups}): "
        + ", ".join(f"{g} {n}" for g, n in sorted(profile.independence_groups.items())),
        "",
        "## Целостность",
    ]
    rejected = sum(r.n_rejected_outcomes for r in reports.values())
    md.append(f"- исходов раньше заморозки (отброшены): {rejected}")
    if integrity is not None:
        md.append(f"- снимков предсказаний проверено {integrity['checked']}, без снимка (до v0.9.6) "
                  f"{integrity['without_snapshot']}, нарушений {len(integrity['violations'])}")
    md.append("- изменение и удаление записей графа запрещено триггерами базы")
    main = {t: r for t, r in reports.items() if not r.legacy_note}
    legacy = {t: r for t, r in reports.items() if r.legacy_note}
    for title, group in (("## Цели", main), ("## Устаревшие цели", legacy)):
        if not group:
            continue
        md += ["", title]
        for target, r in group.items():
            h = r.holdout
            md += [
                "", f"### {target}", "",
                f"- **Вердикт:** `{r.verdict}`. {r.detail}",
                f"- **Уровень утверждений:** `{r.claim_level}`"
                + (f"; не хватает: {'; '.join(r.claim_blockers)}" if r.claim_blockers else ""),
                f"- пары {r.n_pairs}, событий {r.n_positive}, агентов {r.n_agents}, конфигураций {r.n_configurations}, "
                f"пар с Q4 {r.n_q4_pairs}",
                f"- независимость: доноров {r.n_donors}, групп {r.n_independence_groups}, по группам "
                f"{r.outcomes_per_group}" + (f"; ⚠️ {r.independence_warning}" if r.independence_warning else ""),
                f"- вся выборка: ROC-AUC {r.overall.roc_auc}, PR-AUC {r.overall.pr_auc}, Brier {r.overall.brier}",
            ]
            if r.donor_agreement and r.donor_agreement["n_compared"]:
                a = r.donor_agreement
                md.append(f"- согласие доноров: {a['n_agree']} из {a['n_compared']} ({a['agreement_rate']}), "
                          f"расхождения {a['disagreements'] or 'нет'}")
            if r.cohort_warning:
                md.append(f"- ⚠️ {r.cohort_warning}")
            if h:
                md += [
                    f"- holdout: калибровка {h.calibration_n}, проверка {h.test_n}; ROC-AUC {h.trust_score.roc_auc}, "
                    f"CI по {_UNIT[h.bootstrap_unit]} {h.roc_auc_ci}, по конфигурациям {h.roc_auc_ci_by_genome}",
                    f"- baseline «история агента»: ROC-AUC {h.baseline_agent_history.roc_auc}, CI разницы "
                    f"{h.auc_difference_vs_agent_history_ci}. В framework_evaluation агент и есть фреймворк, "
                    f"так что это и baseline по фреймворку",
                ]
            md += _breakdown_markdown(r, target)
            if r.legacy_note:
                md.append(f"- {r.legacy_note}")
    md += ["", "Пороги и допустимые формулировки: docs/VALIDATION_PROTOCOL.md, раздел 6.", ""]
    return "\n".join(md)
