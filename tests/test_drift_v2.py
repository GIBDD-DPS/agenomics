"""
test_drift_v2.py — тесты DriftMonitor v2 (v0.6.0).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.6.0
"""

from agenomics.drift import DriftMonitorV2
from benchmark.scenarios import DRIFT_SCENARIOS_V2


def _run_scenario(name):
    scores = DRIFT_SCENARIOS_V2[name]()
    monitor = DriftMonitorV2()
    reports = []
    for s in scores:
        monitor.record("agent", s)
        reports.append(monitor.report("agent"))
    return reports


def test_no_drift_never_alerts():
    """Ключевой тест против false positives: обычный шум не должен
    вызывать alert ни разу за весь сценарий."""
    reports = _run_scenario("no_drift")
    computed = [r for r in reports if r.severity != "insufficient_data"]
    assert all(not r.alert for r in computed)


def test_mild_degradation_is_eventually_detected():
    """Прямое исправление находки v1: mild-деградация НЕ обнаруживалась
    вовсе за 15 шагов. v2 должна обнаружить её в пределах сценария (20 шагов)."""
    reports = _run_scenario("mild")
    computed = [r for r in reports if r.severity != "insufficient_data"]
    assert any(r.alert for r in computed), "v2 должна обнаруживать mild-деградацию — это была находка v1"


def test_severe_detected_faster_than_mild():
    mild_reports = [r for r in _run_scenario("mild") if r.severity != "insufficient_data"]
    severe_reports = [r for r in _run_scenario("severe") if r.severity != "insufficient_data"]
    mild_first_alert = next(i for i, r in enumerate(mild_reports) if r.alert)
    severe_first_alert = next(i for i, r in enumerate(severe_reports) if r.alert)
    assert severe_first_alert < mild_first_alert


def test_sudden_drop_detected_immediately():
    reports = _run_scenario("sudden")
    computed = [r for r in reports if r.severity != "insufficient_data"]
    # Момент падения — drop_at=10 (см. scenarios.py) — должен дать alert
    # практически сразу (в пределах 1 снимка), а не с задержкой в шаги.
    alert_indices = [i for i, r in enumerate(computed) if r.alert]
    assert alert_indices, "sudden-падение должно быть обнаружено"
    assert alert_indices[0] <= 10, "задержка обнаружения sudden-события не должна превышать сам момент события"


def test_recovery_is_detected():
    reports = _run_scenario("recovery")
    assert any(r.recovered for r in reports), "восстановление после деградации должно быть отмечено хотя бы раз"


def test_oscillation_does_not_falsely_trigger_sustained_severe():
    """Колебание без тренда не должно накапливать 'severe' — это была бы
    ложная тревога о деградации там, где её нет, только шум."""
    reports = _run_scenario("oscillation")
    computed = [r for r in reports if r.severity != "insufficient_data"]
    assert all(r.severity != "severe" for r in computed)
    assert all(r.severity != "moderate" for r in computed)


def test_oscillation_stabilizes_to_volatile_once_window_fills():
    """Честно документированный transient: в первые ~2 шага (до заполнения
    rolling_window) возможна неточная классификация sudden/volatile.
    После заполнения окна — паттерн должен стабилизироваться."""
    reports = _run_scenario("oscillation")
    computed = [r for r in reports if r.severity != "insufficient_data"]
    stable_part = computed[6:]  # после заполнения rolling_window=8 (с учётом baseline_window=3)
    assert all(r.severity != "sudden" for r in stable_part), (
        "После заполнения rolling window колебание не должно давать 'sudden' — "
        "если тест падает, значит регрессия калибровки volatile/sudden"
    )


def test_insufficient_data_before_baseline_window():
    monitor = DriftMonitorV2(baseline_window=3)
    monitor.record("x", 80)
    monitor.record("x", 81)
    report = monitor.report("x")
    assert report.severity == "insufficient_data"


def test_sign_change_counter_distinguishes_oscillation_from_single_step():
    monitor = DriftMonitorV2()
    # Единичный устойчивый скачок — 1 смена знака (или 0)
    single_step_diffs = [0, 0, -30, 0, 0]
    assert monitor._count_sign_changes(single_step_diffs) <= 1
    # Колебание — много смен знака
    oscillating_diffs = [15, -15, 15, -15, 15]
    assert monitor._count_sign_changes(oscillating_diffs) >= 3
