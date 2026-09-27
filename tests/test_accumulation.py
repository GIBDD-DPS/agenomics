# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_accumulation.py. Scorecard накопления доказательств (v0.9.6).

Проект: Prizolov Lab
"""

import json
import os
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO

from agenomics import ACCUMULATION_TARGETS, EvidenceStore, accumulation_scorecard, scorecard_text

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _store(path=":memory:"):
    store = EvidenceStore(path)
    store.register_donor("runtime", "execution", "Runtime", "runtime")
    store.register_donor("checker", "outcome", "Task checker", "task_checker")
    for i, version in enumerate(["0.9.5"] * 3 + ["0.9.6"] * 2):
        obs = store.record_observation(f"agent-{i % 2}", 50.0, "Conditional", trust_model_version=version,
                                       genome_hash=f"cfg-{i}")
        store.record_evidence(obs, "runtime", "execution", "success", "Q1")
        store.record_evidence(obs, "checker", "task_check", "fail" if i == 4 else "pass", "Q3")
        frozen = T0 + timedelta(hours=i)
        for target, donor, outcome_type in (("runtime_failure", "runtime", "execution_error"),
                                            ("task_failure", "checker", "task_failure")):
            pred = store.record_prediction(obs, target, frozen_at=frozen)
            store.record_outcome(pred, donor, outcome_type, target == "task_failure" and i == 4,
                                 observed_at=frozen + timedelta(minutes=1))
    return store


def test_scorecard_rows_and_status():
    rows = {r.metric: r for r in accumulation_scorecard(_store())}
    assert (rows["observations"].current, rows["agents"].current, rows["configurations"].current) == (5, 2, 5)
    assert rows["independence_groups"].current == 2
    assert (rows["evidence_q3"].current, rows["evidence_q4"].current) == (5, 0)
    assert rows["events:task_failure"].current == 1 and rows["events:runtime_failure"].current == 0
    assert all(r.status == "in_progress" for r in rows.values())
    assert rows["evidence_q4"].target == ACCUMULATION_TARGETS["evidence_q4"]


def test_scorecard_cohort_filter_and_text():
    store = _store()
    rows = {r.metric: r for r in accumulation_scorecard(store, trust_model_versions=["0.9.6"])}
    assert rows["observations"].current == 2 and rows["evidence_q3"].current == 2
    text = scorecard_text(list(rows.values()), ["0.9.6"])
    assert "когорта: 0.9.6" in text and "не требования статистической мощности" in text


def test_scorecard_cli_json():
    from agenomics.cli import main
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "e.db")
        _store(db).close()
        with redirect_stdout(StringIO()) as buf:
            assert main(["scorecard", db, "--json"]) == 0
        data = {r["metric"]: r for r in json.loads(buf.getvalue())}
        assert data["observations"]["current"] == 5
        assert main(["scorecard", os.path.join(tmp, "missing.db")]) == 1
