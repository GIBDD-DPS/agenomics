# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_external.py. Внешнее подтверждение исхода, Q4 (v0.9.6).

Проект: Prizolov Lab
"""

from dataclasses import fields
from datetime import datetime, timedelta, timezone

from agenomics import EvidenceStore, ExternalVerification, PredictionView, record_external_outcome


class _Verifier:
    donor_id = "ext.results"

    def __init__(self, occurred=True, delay=timedelta(hours=1), reference="match-18492"):
        self.occurred, self.delay, self.reference = occurred, delay, reference
        self.seen = None

    def verify(self, prediction):
        self.seen = prediction
        return ExternalVerification(
            occurred=self.occurred, outcome_type="task_failure", source_type="external_system",
            source_reference=self.reference, verification_method="api_assertion",
            verified_at=datetime.fromisoformat(prediction.frozen_at) + self.delay,
        )


def _setup():
    store = EvidenceStore(":memory:")
    store.register_donor("ext.results", "outcome", "Results API", "results_api")
    store.register_donor("runtime", "execution", "Runtime", "runtime")
    obs = store.record_observation("a", 40.0, "Conditional")
    pred = store.record_prediction(obs, "task_failure", task_version="match-18492")
    return store, pred


def _expect_value_error(fn):
    try:
        fn()
    except ValueError:
        return
    assert False, "ожидался ValueError"


def test_verifier_does_not_see_trust_score():
    assert "trust_score" not in {f.name for f in fields(PredictionView)}
    store, pred = _setup()
    verifier = _Verifier()
    record_external_outcome(store, pred, verifier)
    assert verifier.seen.task_version == "match-18492" and not hasattr(verifier.seen, "trust_score")


def test_confirmation_not_after_freeze_is_rejected():
    store, pred = _setup()
    _expect_value_error(lambda: record_external_outcome(store, pred, _Verifier(delay=timedelta(0))))
    _expect_value_error(lambda: record_external_outcome(store, pred, _Verifier(delay=-timedelta(minutes=5))))


def test_same_independence_group_cannot_confirm_itself():
    store, pred = _setup()
    store.register_donor("ext.results.v2", "outcome", "Results API v2", "results_api")
    store.record_outcome(pred, "ext.results.v2", "task_failure", True)
    _expect_value_error(lambda: record_external_outcome(store, pred, _Verifier()))


def test_successful_confirmation_is_q4_ground_truth():
    store, pred = _setup()
    store.record_outcome(pred, "runtime", "execution_error", False)
    outcome_id = record_external_outcome(store, pred, _Verifier())
    outcome = [o for o in store.get_predictions()[0].outcomes if o.id == outcome_id][0]
    assert (outcome.quality_level, outcome.verification, outcome.outcome_class) == ("Q4", "ground_truth", "TASK")
    assert outcome.source_reference == "match-18492" and "api_assertion" in outcome.details
    assert store.evidence_profile().n_verified_outcomes == 1


def test_pending_outcome_and_missing_reference():
    store, pred = _setup()

    class _Pending(_Verifier):
        def verify(self, prediction):
            return None

    assert record_external_outcome(store, pred, _Pending()) is None
    _expect_value_error(lambda: record_external_outcome(store, pred, _Verifier(reference="")))
