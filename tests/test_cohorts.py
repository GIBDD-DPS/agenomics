# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_cohorts.py. Типы когорт предсказаний, фильтр когорт в Validation
Engine и scorecard, согласие доноров (docs/specs/validation-data-acquisition-v1.md).

Проект: Prizolov Lab
"""

import json
import os
import sqlite3
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO

import pytest

from agenomics import EvidenceStore, accumulation_scorecard, validate
from agenomics.validation import donor_agreement, validation_report_markdown, validation_report_text

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _store(path=":memory:"):
    """Два агента, по 4 прогона natural и stress_security; у task_failure
    два донора (проверка и судья), которые расходятся на одном прогоне."""
    store = EvidenceStore(path)
    store.register_donor("checker", "outcome", "Task checker", "task_checker")
    store.register_donor("judge", "outcome", "LLM judge", "llm_judge")
    store.register_donor("canary", "security", "Canary", "canary_exact_match")
    i = 0
    for cohort in ("natural", "stress_security"):
        for k in range(4):
            obs = store.record_observation(f"agent-{k % 2}", 40.0 + 10 * k, "Conditional", genome_hash=f"cfg-{k}")
            frozen = T0 + timedelta(hours=i)
            after = frozen + timedelta(minutes=1)
            i += 1
            if cohort == "natural":
                pred = store.record_prediction(obs, "task_failure", frozen_at=frozen, cohort_type="natural")
                store.record_outcome(pred, "checker", "task_failure", k == 0, observed_at=after, source_reference="c")
                store.record_outcome(pred, "judge", "task_failure", k in (0, 1), observed_at=after, source_reference="j")
            else:
                pred = store.record_prediction(obs, "security_incident", frozen_at=frozen, cohort_type="stress_security")
                store.record_outcome(pred, "canary", "prompt_injection_disclosure", k < 2, observed_at=after,
                                     source_reference="canary")
    return store


def test_cohort_type_in_snapshot_and_integrity():
    store = _store()
    p = store.get_predictions()
    assert {x.cohort_type for x in p} == {"natural", "stress_security"}
    assert all(x.snapshot["cohort_type"] == x.cohort_type for x in p)
    assert store.verify_prediction_integrity()["violations"] == []
    with pytest.raises(ValueError):
        obs = store.record_observation("a", 50.0, "Conditional")
        store.record_prediction(obs, "task_failure", cohort_type="stress_everything")


def test_prediction_without_cohort_is_natural_and_keeps_old_snapshot_shape():
    store = EvidenceStore(":memory:")
    obs = store.record_observation("a", 50.0, "Conditional")
    store.record_prediction(obs, "task_failure")
    p = store.get_predictions()[0]
    assert p.cohort_type == "natural" and "cohort_type" not in p.snapshot
    assert store.verify_prediction_integrity()["violations"] == []


def test_old_database_migrates_and_old_rows_count_as_natural():
    """База без колонки cohort_type (0.9.6) получает её миграцией; старые
    предсказания считаются natural, снимки проходят проверку."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "old.db")
        store = EvidenceStore(db)
        store.register_donor("checker", "outcome", "Task checker", "task_checker")
        obs = store.record_observation("a", 50.0, "Conditional")
        pred = store.record_prediction(obs, "task_failure", frozen_at=T0)
        store.record_outcome(pred, "checker", "task_failure", True, observed_at=T0 + timedelta(minutes=1))
        store.close()
        conn = sqlite3.connect(db)
        conn.execute("DROP TRIGGER predictions_no_update")
        conn.execute("ALTER TABLE predictions DROP COLUMN cohort_type")
        conn.commit()
        conn.close()
        store = EvidenceStore(db)
        assert "cohort_type" in {r[1] for r in store._conn.execute("PRAGMA table_info(predictions)")}
        assert store.get_predictions()[0].cohort_type == "natural"
        assert store.verify_prediction_integrity()["violations"] == []
        assert validate(store, target="task_failure").n_pairs == 1
        store.close()


def test_validate_defaults_to_natural_and_filters_cohorts():
    store = _store()
    assert validate(store, target="task_failure").n_pairs == 4
    # security есть только в стресс-когорте: по умолчанию её не видно
    assert validate(store, target="security_incident").n_pairs == 0
    stress = validate(store, target="security_incident", cohort_types=["stress_security"])
    assert stress.n_pairs == 4 and stress.n_positive == 2 and stress.cohort_types == ["stress_security"]
    assert stress.filters["cohort_types"] == ["stress_security"]
    with pytest.raises(ValueError):
        validate(store, target="task_failure", cohort_types=["nope"])


def test_mixed_cohorts_are_flagged():
    store = _store()
    obs = store.record_observation("agent-0", 45.0, "Conditional")
    pred = store.record_prediction(obs, "task_failure", frozen_at=T0 + timedelta(days=1), cohort_type="stress_task")
    store.record_outcome(pred, "checker", "task_failure", True, observed_at=T0 + timedelta(days=1, minutes=1))
    mixed = validate(store, target="task_failure", cohort_types="all")
    assert mixed.n_pairs == 5 and mixed.cohort_types == ["natural", "stress_task"]
    assert "смешаны когорты" in mixed.cohort_warning
    assert "смешаны когорты" in validation_report_text(mixed)
    assert validate(store, target="task_failure").cohort_warning is None


def test_donor_agreement_only_for_same_event_targets():
    store = _store()
    task = validate(store, target="task_failure")
    a = task.donor_agreement
    assert (a["n_compared"], a["n_agree"]) == (4, 3)
    assert a["disagreements"] == {"llm_judge=1,task_checker=0": 1}
    # событие, если его зафиксировал хотя бы один донор (как раньше)
    assert task.n_positive == 2
    assert "Согласие доноров: 3 из 4" in validation_report_text(task)
    security = validate(store, target="security_incident", cohort_types=["stress_security"])
    assert security.donor_agreement is None
    assert donor_agreement([])["agreement_rate"] is None


def test_report_markdown_shows_cohort():
    store = _store()
    reports = {"task_failure": validate(store, target="task_failure")}
    md = validation_report_markdown(store.evidence_profile(), reports, store.verify_prediction_integrity())
    assert "тип когорты: natural" in md and "согласие доноров: 3 из 4" in md


def test_evidence_strength_label_is_not_called_level():
    text = validation_report_text(validate(_store(), target="task_failure"))
    assert "объём выборки" in text and "уровень 'exploratory'" not in text


def test_scorecard_per_cohort():
    store = _store()
    natural = {r.metric: r for r in accumulation_scorecard(store)}
    stress = {r.metric: r for r in accumulation_scorecard(store, cohort_type="stress_security")}
    assert natural["observations"].current == 4 and stress["observations"].current == 4
    assert natural["independence_groups"].current == 2 and stress["independence_groups"].current == 1
    assert "events:security_incident" in stress and stress["events:security_incident"].current == 2
    assert natural["events:task_failure"].target == 25
    with pytest.raises(ValueError):
        accumulation_scorecard(store, cohort_type="nope")


def test_cli_cohort_flags():
    from agenomics.cli import main
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "e.db")
        _store(db).close()
        out = StringIO()
        with redirect_stdout(out):
            assert main(["scorecard", db, "--cohort-type", "all", "--json"]) == 0
        assert set(json.loads(out.getvalue())) == {"natural", "stress_security"}
        out = StringIO()
        with redirect_stdout(out):
            assert main(["scorecard", db, "--cohort-type", "all"]) == 0
        assert "тип когорты: natural" in out.getvalue() and "тип когорты: stress_security" in out.getvalue()
        out = StringIO()
        with redirect_stdout(out):
            assert main(["validate", db, "--target", "security_incident", "--cohort-type", "stress_security",
                         "--json"]) == 0
        assert json.loads(out.getvalue())["security_incident"]["n_pairs"] == 4
        assert main(["validate", db, "--cohort-type", "bogus"]) == 2
