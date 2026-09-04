"""
test_sensitivity.py — тесты Evidence Quality (v0.6.1): Weight Sensitivity,
Threshold Sensitivity, Bootstrap CI.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.6.1
"""

from benchmark.sensitivity import (
    measure_weight_sensitivity,
    measure_threshold_sensitivity,
    bootstrap_ci_compatibility_accuracy,
    run_sensitivity_suite,
    _perturb_weights,
)
from agenomics.trust_score import DEFAULT_TRUST_WEIGHTS


def test_perturb_weights_sums_to_one():
    perturbed = _perturb_weights(DEFAULT_TRUST_WEIGHTS, "accountability", 0.05)
    assert abs(sum(perturbed.values()) - 1.0) < 1e-9


def test_perturb_weights_rejects_impossible_shift():
    """Сдвиг больше суммы остальных весов должен возвращать None, а не
    отрицательный вес."""
    result = _perturb_weights(DEFAULT_TRUST_WEIGHTS, "accountability", 0.90)
    assert result is None


def test_weight_sensitivity_monotonic_with_delta():
    result = measure_weight_sensitivity()
    assert result.status == "computed"
    assert result.raw_data["monotonic"] is True


def test_weight_sensitivity_accountability_is_most_sensitive_axis():
    """Реальная находка: accountability взаимодействует с потолком
    автономности и должна быть заметно чувствительнее остальных осей
    на репрезентативном наборе, включающем TIER_3/autonomous агента."""
    result = measure_weight_sensitivity(deltas=(0.05,))
    per_axis = result.raw_data["by_delta"][0.05]["per_axis_max"]
    assert per_axis["accountability"] > per_axis["transparency"]
    assert per_axis["accountability"] > per_axis["bias_control"]


def test_threshold_sensitivity_no_false_positives():
    result = measure_threshold_sensitivity()
    assert result.status == "computed"
    assert result.raw_data["any_false_positive"] is False


def test_threshold_sensitivity_loose_threshold_can_miss_mild():
    """При достаточно большом mild_threshold обнаружение mild-деградации
    должно ухудшаться (задержка растёт или пропадает вовсе) — иначе
    порог ничего не регулирует, что подозрительно."""
    result = measure_threshold_sensitivity(mild_thresholds=(0.03, 0.10))
    by_threshold = result.raw_data["by_threshold"]
    tight = by_threshold[0.03]["mild_first_alert_at"]
    loose = by_threshold[0.10]["mild_first_alert_at"]
    assert tight is not None
    assert loose is None or loose > tight


def test_bootstrap_ci_reproducible_with_same_seed():
    r1 = bootstrap_ci_compatibility_accuracy(n_bootstrap=200, seed=7)
    r2 = bootstrap_ci_compatibility_accuracy(n_bootstrap=200, seed=7)
    assert r1.value == r2.value
    assert r1.raw_data["ci_low"] == r2.raw_data["ci_low"]
    assert r1.raw_data["ci_high"] == r2.raw_data["ci_high"]


def test_bootstrap_ci_different_seed_can_differ_or_match():
    """Не требуем различия (при очень чистом разделении CI может
    схлопнуться в точку независимо от seed) — только что оба
    результата валидны и в диапазоне [0,1]."""
    r1 = bootstrap_ci_compatibility_accuracy(n_bootstrap=200, seed=1)
    r2 = bootstrap_ci_compatibility_accuracy(n_bootstrap=200, seed=2)
    for r in (r1, r2):
        assert 0.0 <= r.raw_data["ci_low"] <= r.raw_data["ci_high"] <= 1.0


def test_bootstrap_ci_mean_matches_known_full_separation():
    """При полном разделении классов (уже подтверждённом в
    test_compat_ground_truth_v2.py) bootstrap mean должен быть равен 1.0."""
    result = bootstrap_ci_compatibility_accuracy(n_bootstrap=300, seed=42)
    assert result.value == 1.0


def test_run_sensitivity_suite_returns_three_results():
    results = run_sensitivity_suite()
    assert len(results) == 3
    assert all(r.status == "computed" for r in results)
