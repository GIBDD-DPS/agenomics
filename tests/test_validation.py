# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_validation.py. Тесты Validation Engine (v0.9.1).

Синтетические сценарии построены так, что правильный вердикт известен
заранее: score предсказывает исход внутри агента, исход определяется
только тем, какой это агент, score случаен.

Проект: Prizolov Lab
"""

import itertools
import json
import os
import random
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO

from agenomics import EvidenceStore, validate, validation_report_text
from agenomics.validation import (
    average_precision, bootstrap_auc_ci, brier, build_pairs, calibration_table, roc_auc, spearman,
    ValidationPair,
)

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _store():
    store = EvidenceStore(":memory:")
    store.register_donor("runtime", "execution", "Runtime", "runtime")
    store.register_donor("scanner", "security", "Scanner", "regex_scanner")
    store.register_donor("judge", "judge", "Judge", "llm")
    return store


def _add(store, agent_id, score, occurred, step, outcome_type="execution_error", donor="runtime", extra=()):
    obs_id = store.record_observation(agent_id, score, "Conditional", genome_hash=f"cfg-{agent_id}")
    frozen = T0 + timedelta(hours=step)
    pred_id = store.record_prediction(obs_id, "incident_in_run", frozen_at=frozen)
    store.record_outcome(pred_id, donor, outcome_type, occurred, observed_at=frozen + timedelta(minutes=1))
    for extra_donor, extra_type, extra_occurred in extra:
        store.record_outcome(pred_id, extra_donor, extra_type, extra_occurred, observed_at=frozen + timedelta(minutes=2))
    return pred_id


def _populate(store, n_agents, n_runs, make, seed=0):
    rng = random.Random(seed)
    step = 0
    for run in range(n_runs):
        for a in range(n_agents):
            score, occurred = make(rng, a, run)
            _add(store, f"agent-{a}", score, occurred, step)
            step += 1


# --- Сценарии с известным ответом -------------------------------------------

def test_score_that_predicts_within_agent_beats_baseline():
    def make(rng, a, run):
        score = rng.uniform(20, 90)
        return score, rng.random() < (0.9 if score < 55 else 0.1)
    store = _store()
    _populate(store, 10, 20, make)
    report = validate(store)
    assert report.verdict == "signal_beats_baseline", report.detail
    assert report.holdout.trust_score.roc_auc > 0.75
    assert report.holdout.roc_auc_ci[0] > 0.5
    assert report.holdout.bootstrap_unit == "agent"


def test_score_that_only_encodes_agent_identity_does_not_beat_agent_history():
    rates = [0.05, 0.1, 0.2, 0.3, 0.45, 0.55, 0.7, 0.8, 0.9, 0.95]
    # score знает агента, но с ошибкой: агенты 3 и 6 переставлены
    agent_scores = [95, 90, 80, 40, 55, 45, 70, 20, 10, 5]

    def make(rng, a, run):
        return agent_scores[a] + rng.uniform(-2, 2), rng.random() < rates[a]
    store = _store()
    _populate(store, 10, 20, make)
    report = validate(store)
    assert report.verdict == "signal_not_better_than_baseline", report.detail
    assert report.holdout.baseline_agent_history.roc_auc >= report.holdout.trust_score.roc_auc


def test_random_score_shows_no_evidence_of_signal():
    def make(rng, a, run):
        return rng.uniform(20, 90), rng.random() < 0.4
    store = _store()
    _populate(store, 10, 20, make, seed=3)
    report = validate(store)
    assert report.verdict == "no_evidence_of_signal", report.detail
    assert report.holdout.roc_auc_ci[0] <= 0.5 <= report.holdout.roc_auc_ci[1]


def test_insufficient_data_when_few_pairs():
    store = _store()
    _populate(store, 3, 3, lambda rng, a, run: (rng.uniform(20, 90), rng.random() < 0.5))
    report = validate(store)
    assert report.verdict == "insufficient_data"
    assert "проверочной" in report.detail


def test_constant_scores_are_insufficient_not_no_signal():
    """Первые прогоны framework_evaluation: истории нет, у всех score 51."""
    store = _store()
    _populate(store, 10, 10, lambda rng, a, run: (51.0, rng.random() < 0.3))
    report = validate(store)
    assert report.verdict == "insufficient_data"
    assert "одинаковый Trust Score" in report.detail


def test_empty_store():
    report = validate(_store())
    assert report.verdict == "insufficient_data" and report.n_pairs == 0
    assert "Validation Engine: insufficient_data" in validation_report_text(report)


# --- Сборка пар и фильтры -----------------------------------------------------

def test_infrastructure_failures_excluded_entirely():
    store = _store()
    _add(store, "a", 40.0, True, 0, outcome_type="infrastructure_error",
         extra=[("scanner", "secret_leak", False)])
    _add(store, "a", 60.0, False, 1, extra=[("scanner", "secret_leak", False)])
    pairs = build_pairs(store)
    assert [p.trust_score for p in pairs] == [60.0]
    # без исключения прогон с инфраструктурной ошибкой попал бы как "без утечки"
    assert len(build_pairs(store, exclude_outcome_types=())) == 2


def test_prediction_without_outcome_is_unknown_not_negative():
    store = _store()
    obs_id = store.record_observation("a", 50.0, "Conditional")
    store.record_prediction(obs_id, "incident_in_run")
    assert build_pairs(store) == []


def test_filters_by_outcome_type_group_and_target():
    store = _store()
    _add(store, "a", 30.0, False, 0, extra=[("scanner", "secret_leak", True), ("judge", "unsafe", False)])
    assert build_pairs(store)[0].occurred is True  # любой подходящий исход
    assert build_pairs(store, outcome_types=["execution_error"])[0].occurred is False
    assert build_pairs(store, independence_groups=["regex_scanner"])[0].occurred is True
    assert build_pairs(store, independence_groups=["llm"])[0].occurred is False
    assert build_pairs(store, target="something_else") == []
    assert build_pairs(store)[0].genome_hash == "cfg-a"


def test_report_counts_agents_and_configurations():
    store = _store()
    _populate(store, 4, 3, lambda rng, a, run: (rng.uniform(20, 90), rng.random() < 0.5))
    report = validate(store)
    assert report.n_agents == 4 and report.n_configurations == 4 and report.n_pairs == 12


# --- Метрики -------------------------------------------------------------------

def _brute_force_auc(scores, labels):
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p, n in itertools.product(pos, neg))
    return wins / (len(pos) * len(neg))


def test_roc_auc_matches_brute_force_with_ties():
    rng = random.Random(7)
    scores = [rng.choice([10, 20, 30, 40, 50]) for _ in range(80)]
    labels = [rng.random() < 0.4 for _ in range(80)]
    assert abs(roc_auc(scores, labels) - _brute_force_auc(scores, labels)) < 1e-12
    assert roc_auc([1, 2, 3], [True, True, True]) is None
    assert roc_auc([5, 5, 5, 5], [True, False, True, False]) == 0.5


def test_average_precision_known_value_and_ties():
    assert abs(average_precision([0.9, 0.8, 0.7, 0.6], [True, False, True, False]) - (0.5 + 0.5 * 2 / 3)) < 1e-12
    # все с одним score: один порог, precision = base rate
    assert average_precision([1, 1, 1, 1], [True, False, False, False]) == 0.25
    assert average_precision([1, 2], [False, False]) is None


def test_brier_calibration_and_spearman():
    assert brier([0.0, 1.0], [False, True]) == 0.0
    assert brier([0.5, 0.5], [False, True]) == 0.25
    table, ece = calibration_table([0.05, 0.05, 0.95, 0.95], [False, False, True, True])
    assert [b.n for b in table] == [2, 2] and ece == 0.05
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert spearman([1, 2], [1, 2]) is None


def test_bootstrap_ci_none_when_mostly_one_class():
    pairs = [ValidationPair(i, f"a{i}", 50.0 + i, i == 0, T0) for i in range(20)]
    assert bootstrap_auc_ci(pairs, n_resamples=200) is None


def test_holdout_is_temporal():
    store = _store()
    _populate(store, 5, 10, lambda rng, a, run: (rng.uniform(20, 90), rng.random() < 0.5))
    report = validate(store, calibration_fraction=0.6)
    assert report.holdout.calibration_n == 30 and report.holdout.test_n == 20
    assert report.holdout.split_at == (T0 + timedelta(hours=30)).isoformat()


def test_bootstrap_unit_falls_back_to_observation_for_few_agents():
    store = _store()
    _populate(store, 2, 40, lambda rng, a, run: (rng.uniform(20, 90), rng.random() < 0.5))
    assert validate(store).holdout.bootstrap_unit == "observation"


def test_calibration_fraction_validated():
    try:
        validate(_store(), calibration_fraction=1.0)
        assert False
    except ValueError:
        pass


# --- CLI -------------------------------------------------------------------------

def test_cli_validate_text_and_json():
    from agenomics.cli import main
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "e.db")
        store = EvidenceStore(db)
        store.register_donor("runtime", "execution", "Runtime", "runtime")
        _populate(store, 10, 20, lambda rng, a, run: (rng.uniform(20, 90), rng.random() < 0.4))
        store.close()

        out = StringIO()
        with redirect_stdout(out):
            assert main(["validate", db]) == 0
        assert "Validation Engine [incident_in_run]:" in out.getvalue()

        out = StringIO()
        with redirect_stdout(out):
            assert main(["validate", db, "--json", "--outcome-type", "execution_error"]) == 0
        data = json.loads(out.getvalue())["incident_in_run"]
        assert data["verdict"] in ("no_evidence_of_signal", "signal_not_better_than_baseline",
                                   "signal_beats_baseline", "insufficient_data")
        assert data["filters"]["exclude_outcome_types"] == ["infrastructure_error"]
        assert main(["validate", os.path.join(tmp, "missing.db")]) == 1


def test_beating_baseline_requires_ci_of_difference_above_zero():
    """Точечное AUC(score) > AUC(baseline) недостаточно: разница должна
    быть отличима от шума. Сценарий, где score лишь кодирует агента, на
    20 seed ни разу не должен дать signal_beats_baseline."""
    rates = [0.05, 0.1, 0.2, 0.3, 0.45, 0.55, 0.7, 0.8, 0.9, 0.95]
    agent_scores = [95, 90, 80, 40, 55, 45, 70, 20, 10, 5]
    verdicts = set()
    for seed in range(20):
        store = _store()
        _populate(store, 10, 20, lambda rng, a, run: (agent_scores[a] + rng.uniform(-2, 2), rng.random() < rates[a]),
                  seed=seed)
        report = validate(store)
        verdicts.add(report.verdict)
        if report.verdict == "signal_not_better_than_baseline":
            assert report.holdout.auc_difference_vs_agent_history_ci[0] <= 0
    assert "signal_beats_baseline" not in verdicts



# --- v0.9.2: цели, независимость, повторная проверка времени -----------------

def test_mixed_targets_require_explicit_target():
    store = _store()
    obs_id = store.record_observation("a", 50.0, "Conditional")
    for target, donor, outcome_type in (("runtime_failure", "runtime", "execution_error"),
                                        ("security_incident", "scanner", "secret_leak")):
        pred = store.record_prediction(obs_id, target, frozen_at=T0)
        store.record_outcome(pred, donor, outcome_type, False, observed_at=T0 + timedelta(minutes=1))
    try:
        validate(store)
        assert False, "смешивание целей должно быть запрещено"
    except ValueError as e:
        assert "runtime_failure" in str(e)
    from agenomics import validate_all_targets, prediction_targets
    assert prediction_targets(store) == ["runtime_failure", "security_incident"]
    reports = validate_all_targets(store)
    assert set(reports) == {"runtime_failure", "security_incident"}
    assert all(r.n_pairs == 1 for r in reports.values())


def test_report_counts_donors_groups_and_verified_pairs():
    store = _store()
    store.register_donor("human", "human", "Reviewer", "human")
    pred = _add(store, "a", 40.0, True, 0, extra=[("judge", "execution_error", True)])
    store.record_outcome(pred, "human", "execution_error", True, verification="ground_truth",
                         observed_at=T0 + timedelta(minutes=5))
    _add(store, "b", 60.0, False, 1)
    report = validate(store)
    assert report.n_donors == 3
    assert report.independence_groups == ["human", "llm", "runtime"]
    assert report.n_verified_pairs == 1
    assert "Независимость: доноров 3" in validation_report_text(report)


def test_outcomes_observed_before_freeze_are_rejected():
    """Имитация импортированной или исправленной вручную базы: исход с
    временем раньше заморозки в обход record_outcome()."""
    store = _store()
    pred = _add(store, "a", 40.0, False, 0)
    store._conn.execute(
        "INSERT INTO outcomes (prediction_id, donor_id, outcome_type, occurred, verification, observed_at) "
        "VALUES (?, 'scanner', 'secret_leak', 1, 'automated', ?)",
        (pred, (T0 - timedelta(hours=1)).isoformat()),
    )
    store._conn.commit()
    pairs = build_pairs(store)
    assert len(pairs) == 1 and pairs[0].occurred is False  # подложенный исход не засчитан
    report = validate(store)
    assert report.n_rejected_outcomes == 1
    assert "отброшено исходов раньше заморозки: 1" in validation_report_text(report)


def test_cli_without_target_reports_every_target():
    from agenomics.cli import main
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "e.db")
        store = EvidenceStore(db)
        store.register_donor("runtime", "execution", "Runtime", "runtime")
        obs_id = store.record_observation("a", 50.0, "Conditional")
        for target in ("runtime_failure", "task_failure"):
            pred = store.record_prediction(obs_id, target, frozen_at=T0)
            store.record_outcome(pred, "runtime", "x", False, observed_at=T0 + timedelta(minutes=1))
        store.close()
        out = StringIO()
        with redirect_stdout(out):
            assert main(["validate", db]) == 0
        text = out.getvalue()
        assert "Validation Engine [runtime_failure]" in text and "Validation Engine [task_failure]" in text


# --- v0.9.5: устаревшая цель, шапка с объёмом и качеством данных -------------

def test_legacy_target_is_marked_and_reported_last():
    store = _store()
    obs_id = store.record_observation("a", 50.0, "Conditional")
    for target, donor, outcome_type in (("incident_in_run", "runtime", "execution_error"),
                                        ("runtime_failure", "runtime", "execution_error"),
                                        ("security_incident", "scanner", "secret_leak")):
        pred = store.record_prediction(obs_id, target, frozen_at=T0)
        store.record_outcome(pred, donor, outcome_type, False, observed_at=T0 + timedelta(minutes=1))
    from agenomics import prediction_targets, validate_all_targets
    assert prediction_targets(store) == ["runtime_failure", "security_incident", "incident_in_run"]
    reports = validate_all_targets(store)
    assert reports["incident_in_run"].legacy_note and reports["runtime_failure"].legacy_note is None
    text = validation_report_text(reports["incident_in_run"])
    assert "(устаревшая цель)" in text and "runtime_failure" in text


def test_cli_prints_evidence_profile_before_reports():
    from agenomics.cli import main
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "e.db")
        store = EvidenceStore(db)
        store.register_donor("runtime", "execution", "Runtime", "runtime")
        obs_id = store.record_observation("a", 50.0, "Conditional", genome_hash="cfg")
        store.record_evidence(obs_id, "runtime", "execution", "success", "Q1")
        pred = store.record_prediction(obs_id, "runtime_failure", frozen_at=T0)
        store.record_outcome(pred, "runtime", "execution_error", False, observed_at=T0 + timedelta(minutes=1))
        store.close()
        out = StringIO()
        with redirect_stdout(out):
            assert main(["validate", db]) == 0
        text = out.getvalue()
        assert text.index("База: наблюдений 1") < text.index("Validation Engine [runtime_failure]")
        assert "Q1 1" in text and "Q4 0" in text and "с исходом 1" in text
        out = StringIO()
        with redirect_stdout(out):
            assert main(["validate", db, "--json"]) == 0
        data = json.loads(out.getvalue())
        assert data["evidence_profile"]["evidence_by_quality"]["Q1"] == 1
        assert "runtime_failure" in data
