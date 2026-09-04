"""
sensitivity.py — Evidence Quality для Agenomics Synthetic Benchmark Suite (v0.6.1).

Автор: Dm.Andreyanov
Проект: Prizolov Lab

Не новый функционал, а укрепление существующего: насколько устойчивы
цифры бенчмарка к малым изменениям весов/порогов, и насколько широк
реальный разброс метрик при пересемплировании (bootstrap).

ВАЖНО: bootstrap CI здесь считается на СИНТЕТИЧЕСКОМ ground truth —
это доверительный интервал по отношению к вариативности конкретного
синтетического распределения случаев, а НЕ доверительный интервал
относительно реального мира. Та же оговорка, что и во всём остальном
бенчмарке (см. benchmark/README.md).
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from agenomics import AgentGenome, TrustScorer, CompatibilityScorer, DriftMonitorV2
from agenomics.trust_score import DEFAULT_TRUST_WEIGHTS

from .metrics import BenchmarkResult
from .scenarios import (
    quality_spectrum_genomes,
    generate_compatibility_ground_truth,
    drift_scenario_no_drift,
    drift_scenario_mild,
)

# --- 1. Weight Sensitivity ---------------------------------------------------


def _perturb_weights(base_weights: Dict[str, float], axis: str, delta: float) -> Optional[Dict[str, float]]:
    """Увеличивает base_weights[axis] на delta, пропорционально уменьшая
    остальные оси так, чтобы сумма весов осталась 1.0. Возвращает None,
    если такая перестановка даёт отрицательный вес (delta слишком велика)."""
    others = [a for a in base_weights if a != axis]
    other_total = sum(base_weights[a] for a in others)
    new_weights = dict(base_weights)
    new_weights[axis] = base_weights[axis] + delta
    if new_weights[axis] < 0 or new_weights[axis] > 1:
        return None
    if other_total > 0:
        scale = (other_total - delta) / other_total
        if scale < 0:
            return None
        for a in others:
            new_weights[a] = base_weights[a] * scale
    return new_weights


def _representative_genomes() -> List[AgentGenome]:
    """Небольшой, но разнородный набор геномов для проверки
    чувствительности — не весь benchmark, а срез по спектру качества
    плюс один TIER_3/autonomous случай, где взаимодействуют tier-penalty
    и потолок автономности."""
    spectrum = [g for g, _ in quality_spectrum_genomes(n=5)]
    tier3_case = AgentGenome(
        id="sensitivity-finance", domain="finance", autonomy="autonomous",
        transparency=75, bias_control=80, data_safety=85, drift_rate=0.15, has_ledger=False,
    )
    return spectrum + [tier3_case]


def measure_weight_sensitivity(deltas: Tuple[float, ...] = (0.01, 0.03, 0.05, 0.10)) -> BenchmarkResult:
    """
    Для каждой величины сдвига веса (delta) и каждой оси считает, насколько
    меняется итоговый Trust Score на наборе репрезентативных геномов —
    в обе стороны (+delta/-delta). Отчёт: max и средний |Δscore| на каждую
    величину сдвига. Больше |Δscore| при том же delta = формула более
    чувствительна к конкретному весу этой оси.
    """
    genomes = _representative_genomes()
    base_scorer = TrustScorer(weights=DEFAULT_TRUST_WEIGHTS)
    base_scores = {g.id: base_scorer.score(g).score for g in genomes}

    by_delta = {}
    for delta in deltas:
        changes = []
        per_axis_max = {}
        for axis in DEFAULT_TRUST_WEIGHTS:
            axis_changes = []
            for sign in (1, -1):
                perturbed = _perturb_weights(DEFAULT_TRUST_WEIGHTS, axis, sign * delta)
                if perturbed is None:
                    continue
                scorer = TrustScorer(weights=perturbed)
                for g in genomes:
                    change = abs(scorer.score(g).score - base_scores[g.id])
                    changes.append(change)
                    axis_changes.append(change)
            if axis_changes:
                per_axis_max[axis] = round(max(axis_changes), 2)

        by_delta[delta] = {
            "max_change": round(max(changes), 2) if changes else None,
            "avg_change": round(sum(changes) / len(changes), 2) if changes else None,
            "per_axis_max": per_axis_max,
        }

    # Ожидание: изменения должны расти монотонно вместе с delta — если нет,
    # это подозрительно (нелинейный артефакт формулы, стоит расследовать).
    ordered_deltas = sorted(by_delta.keys())
    max_changes = [by_delta[d]["max_change"] for d in ordered_deltas]
    monotonic = all(max_changes[i] <= max_changes[i + 1] + 1e-9 for i in range(len(max_changes) - 1))

    return BenchmarkResult(
        metric="Weight Sensitivity",
        status="computed",
        value=by_delta[ordered_deltas[-1]]["max_change"],  # худший случай при самом большом сдвиге
        detail=(
            f"Максимальное и среднее |Δscore| при сдвиге весов на "
            f"{list(ordered_deltas)}: {by_delta}. "
            f"Монотонный рост изменения вместе с delta: {monotonic} "
            f"(если False — нелинейный артефакт, стоит расследовать отдельно)."
        ),
        raw_data={"by_delta": by_delta, "monotonic": monotonic},
    )


# --- 2. Threshold Sensitivity (Drift) ----------------------------------------


def measure_threshold_sensitivity(
    mild_thresholds: Tuple[float, ...] = (0.03, 0.05, 0.07, 0.10),
) -> BenchmarkResult:
    """
    Для каждого значения mild_threshold в DriftMonitorV2 проверяет:
      1. false positive rate на no_drift (не должно быть alert НИ ПРИ
         ОДНОМ разумном значении порога — если есть, порог слишком мал);
      2. задержку обнаружения mild-деградации (должна расти вместе с
         порогом — более строгий порог реагирует позже, это ожидаемый
         компромисс чувствительность/ложные срабатывания).
    """
    no_drift_scores = drift_scenario_no_drift()
    mild_scores = drift_scenario_mild()

    results = {}
    for mt in mild_thresholds:
        monitor_a = DriftMonitorV2(mild_threshold=mt)
        false_positive = False
        for s in no_drift_scores:
            monitor_a.record("a", s)
            if monitor_a.report("a").alert:
                false_positive = True
                break

        monitor_b = DriftMonitorV2(mild_threshold=mt)
        first_alert = None
        for i, s in enumerate(mild_scores):
            monitor_b.record("b", s)
            r = monitor_b.report("b")
            if r.alert and first_alert is None:
                first_alert = i

        results[mt] = {"false_positive_on_no_drift": false_positive, "mild_first_alert_at": first_alert}

    any_false_positive = any(r["false_positive_on_no_drift"] for r in results.values())
    lags = [(mt, r["mild_first_alert_at"]) for mt, r in results.items() if r["mild_first_alert_at"] is not None]
    lags.sort()
    lag_increases_with_threshold = all(
        lags[i][1] <= lags[i + 1][1] for i in range(len(lags) - 1)
    ) if len(lags) >= 2 else None

    return BenchmarkResult(
        metric="Threshold Sensitivity (Drift mild_threshold)",
        status="computed",
        value=0.0 if any_false_positive else 1.0,
        detail=(
            f"Результаты по порогам {list(mild_thresholds)}: {results}. "
            f"Ложные срабатывания на no_drift при любом из проверенных порогов: "
            f"{any_false_positive} (должно быть False). "
            f"Задержка растёт вместе с порогом (ожидаемый компромисс): "
            f"{lag_increases_with_threshold}."
        ),
        raw_data={"by_threshold": results, "any_false_positive": any_false_positive},
    )


# --- 3. Bootstrap Confidence Interval для Compatibility Accuracy ------------


def bootstrap_ci_compatibility_accuracy(
    cases_per_category: int = 30, n_bootstrap: int = 1000, seed: int = 42,
) -> BenchmarkResult:
    """
    Bootstrap 95% CI для Compatibility Accuracy v2 (n=270). ЧЕСТНАЯ ОГОВОРКА:
    это доверительный интервал ОТНОСИТЕЛЬНО ВАРИАТИВНОСТИ СИНТЕТИЧЕСКОГО
    распределения случаев — он показывает, насколько сама метрика "accuracy"
    неустойчива при пересемплировании ЭТОГО набора, а не доверительный
    интервал относительно реального мира (реальных данных здесь всё ещё нет).

    seed зафиксирован для воспроизводимости — тот же seed даёт те же числа.
    """
    cases = generate_compatibility_ground_truth(cases_per_category)
    scorer = CompatibilityScorer()

    scored: List[Tuple[float, str]] = []
    for case in cases:
        if case.expected_label not in ("compatible", "conflicting"):
            continue
        result = scorer.score_pair(case.genome_a, case.genome_b)
        scored.append((result.score, case.expected_label))

    rng = random.Random(seed)
    n = len(scored)
    accuracies = []
    for _ in range(n_bootstrap):
        sample = [scored[rng.randrange(n)] for _ in range(n)]
        compatible = [s for s, label in sample if label == "compatible"]
        conflicting = [s for s, label in sample if label == "conflicting"]
        if not compatible or not conflicting:
            continue
        max_conflicting = max(conflicting)
        min_compatible = min(compatible)
        correct = sum(1 for s in compatible if s > max_conflicting)
        correct += sum(1 for s in conflicting if s < min_compatible)
        accuracies.append(correct / len(sample))

    accuracies.sort()
    n_acc = len(accuracies)
    lo = accuracies[int(0.025 * n_acc)]
    hi = accuracies[min(int(0.975 * n_acc), n_acc - 1)]
    mean_acc = sum(accuracies) / n_acc

    return BenchmarkResult(
        metric="Compatibility Accuracy v2 — Bootstrap 95% CI",
        status="computed",
        value=round(mean_acc, 4),
        detail=(
            f"{n_bootstrap} bootstrap-пересемплирований (seed={seed}) на "
            f"{n} случаях (compatible+conflicting, ambiguous исключены): "
            f"mean={mean_acc:.4f}, 95% CI=[{lo:.4f}, {hi:.4f}]. "
            f"Это интервал по вариативности СИНТЕТИЧЕСКОГО набора, не "
            f"доверительный интервал относительно реального мира."
        ),
        raw_data={"mean": mean_acc, "ci_low": lo, "ci_high": hi, "n_bootstrap": n_bootstrap, "seed": seed},
    )


def run_sensitivity_suite() -> List[BenchmarkResult]:
    return [
        measure_weight_sensitivity(),
        measure_threshold_sensitivity(),
        bootstrap_ci_compatibility_accuracy(),
    ]
