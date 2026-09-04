"""
test_benchmark.py — тесты Agenomics Synthetic Benchmark Suite.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.6.0
"""

from benchmark.metrics import (
    measure_reproducibility,
    measure_behavioral_predictability_consistency,
    measure_trust_calibration_consistency,
    measure_compatibility_accuracy,
    measure_drift_detection_lag,
    measure_incident_correlation,
    run_all_benchmarks,
    _pearson_correlation,
)


def test_pearson_correlation_perfect_positive():
    assert abs(_pearson_correlation([1, 2, 3, 4], [1, 2, 3, 4]) - 1.0) < 1e-9


def test_pearson_correlation_perfect_negative():
    assert abs(_pearson_correlation([1, 2, 3, 4], [4, 3, 2, 1]) - (-1.0)) < 1e-9


def test_pearson_correlation_zero_variance_returns_zero():
    assert _pearson_correlation([1, 1, 1], [1, 2, 3]) == 0.0


def test_reproducibility_is_perfect():
    """Детерминированная формула ДОЛЖНА давать 1.0 — если нет, это баг."""
    result = measure_reproducibility(n_runs=20)
    assert result.status == "computed"
    assert result.value == 1.0


def test_behavioral_predictability_strongly_negative():
    """drift_rate растёт -> Predictability падает — сильная отрицательная корреляция."""
    result = measure_behavioral_predictability_consistency()
    assert result.status == "computed"
    assert result.value < -0.95  # почти идеальная монотонность


def test_trust_calibration_strongly_positive():
    result = measure_trust_calibration_consistency()
    assert result.status == "computed"
    assert result.value > 0.95  # высокая, но не обязательно ровно 1.0


def test_compatibility_accuracy_full_separation_on_ground_truth():
    result = measure_compatibility_accuracy()
    assert result.status == "computed"
    assert result.value == 1.0  # ручные случаи специально сконструированы чётко


def test_drift_detection_lag_computed_for_at_least_one_severity():
    result = measure_drift_detection_lag()
    assert result.status == "computed"
    assert result.raw_data["lags_by_severity"]["severe"] is not None
    assert result.raw_data["lags_by_severity"]["moderate"] is not None


def test_incident_correlation_honestly_not_computable():
    """Критический тест: эта метрика НЕ должна тихо превращаться в
    fake-число. Явный статус not_computable — часть контракта."""
    result = measure_incident_correlation()
    assert result.status == "not_computable"
    assert result.value is None
    assert "реальных" in result.detail or "real" in result.detail.lower()


def test_run_all_benchmarks_returns_eight_results():
    results = run_all_benchmarks()
    assert len(results) == 8
    statuses = {r.status for r in results}
    assert statuses == {"computed", "not_computable"}
    not_computable = [r for r in results if r.status == "not_computable"]
    assert len(not_computable) == 1
    assert not_computable[0].metric == "Incident Correlation"
