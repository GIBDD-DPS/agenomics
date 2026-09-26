# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .evaluation import _evidence_strength

# Прогон, упавший из-за окружения, не проверяет поведение агента: агент
# не работал. Такие предсказания исключаются целиком, а не считаются
# "без инцидента" по остальным донорам.
DEFAULT_EXCLUDED_OUTCOME_TYPES = ("infrastructure_error",)

# [v0.9.5] Цели, которые больше не создаются, но остаются в накопленных
# базах. Отчёт по ним строится (данные есть), но помечается и идёт после
# основных целей: общая цель "был ли инцидент" смешивает разные события и
# не сравнима с раздельными целями.
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
        # [после v0.9.5] Когорта по версии модели доверия: база накопительная, и
        # прогоны разных версий Trust Score проверяются по отдельности.
        if trust_model_versions is not None and version_by_obs.get(p.observation_id) not in trust_model_versions:
            continue
        frozen = _parse_time(p.frozen_at)
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
                          independence_groups, verification, agent_id)[0]


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
) -> Optional[Tuple[float, float]]:
    """95% интервал AUC. by_agent: ресэмплируются агенты целиком со всеми
    их прогонами (кластерный bootstrap), иначе отдельные наблюдения.
    None при меньше чем двух примерах любого класса: с одним примером
    каждый ресэмпл, где он есть, даёт вырожденный AUC, и интервал вроде
    (1.0, 1.0) только вводил бы в заблуждение."""
    if not _has_both_classes(pairs):
        return None
    return _cluster_bootstrap(
        pairs, (lambda p: p.agent_id) if by_agent else (lambda p: str(p.prediction_id)),
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
    calibration_fraction: float = 0.6,
    min_test_pairs: int = 30,
    min_class_count: int = 5,
    min_agents_for_cluster_bootstrap: int = 5,
) -> ValidationReport:
    """Сопоставляет замороженные предсказания с исходами. См. docstring модуля."""
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("calibration_fraction должен быть в (0, 1)")
    filters = {
        "target": target, "outcome_types": list(outcome_types) if outcome_types else None,
        "exclude_outcome_types": list(exclude_outcome_types),
        "independence_groups": list(independence_groups) if independence_groups else None,
        "verification": list(verification) if verification else None, "agent_id": agent_id,
        "trust_model_versions": list(trust_model_versions) if trust_model_versions else None,
    }
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
        trust_model_versions,
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
    return report


def validate_all_targets(store, **kwargs) -> Dict[str, "ValidationReport"]:
    """validate() отдельно для каждой цели предсказаний в базе."""
    kwargs.pop("target", None)
    return {target: validate(store, target=target, **kwargs) for target in prediction_targets(store)}


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
        f"уровень доказательств '{report.evidence_strength}', агентов {report.n_agents}."
    )


def evidence_profile_text(profile, reports: Optional[Dict[str, "ValidationReport"]] = None) -> str:
    """Шапка отчёта: объём и качество данных до вердиктов по целям. Без
    неё по отчёту не видно, на чём он построен.

    [после v0.9.5] Уровни N раздельно: предсказания, наблюдения (прогоны) с
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
        f"конфигураций {report.n_configurations}, уровень '{report.evidence_strength}'",
        f"  Независимость: доноров {report.n_donors}, групп {report.n_independence_groups} "
        f"{report.independence_groups}, подтверждённых человеком/реальностью пар {report.n_verified_pairs}"
        + (f", отброшено исходов раньше заморозки: {report.n_rejected_outcomes}" if report.n_rejected_outcomes else ""),
        f"  Вся выборка: ROC-AUC {o.roc_auc}, PR-AUC {o.pr_auc} (base rate {o.base_rate}), "
        f"Brier {o.brier}, ECE {report.expected_calibration_error}",
        f"  Уровень агента: Spearman(средний score, частота событий) = {report.agent_level_spearman}",
    ]
    if h:
        lines += [
            f"  Holdout: калибровка {h.calibration_n}, проверка {h.test_n} (с {h.split_at})",
            f"    Trust Score: ROC-AUC {h.trust_score.roc_auc} CI {h.roc_auc_ci}, PR-AUC {h.trust_score.pr_auc}, "
            f"Brier {h.trust_score.brier}",
            f"    Порог риска {h.risk_threshold}: precision {h.precision}, recall {h.recall}, F1 {h.f1}, "
            f"accuracy {h.accuracy} (majority class {h.baseline_majority_accuracy})",
            f"    Baseline история агента: ROC-AUC {h.baseline_agent_history.roc_auc} "
            f"(CI разницы с Trust Score {h.auc_difference_vs_agent_history_ci}), "
            f"Brier {h.baseline_agent_history.brier}; константа: Brier {h.baseline_constant_brier}",
        ]
    lines.append("  Brier и калибровка считаются по наивной вероятности p = (100 - score) / 100.")
    return "\n".join(lines)
