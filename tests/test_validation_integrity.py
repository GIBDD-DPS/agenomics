# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_validation_integrity.py. Validation Integrity Audit v2: объём выборки
отчёта по когорте, исключения по классу, период (--since), разбивка по
условиям и моделям, правило вывода сценария, раздел Q4.

Проект: Prizolov Lab
"""

import json
import os
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO

from agenomics import EvidenceStore, accumulation_scorecard, validate
from agenomics.validation import (
    SCENARIO_RETIREMENT, cohort_summary, scenario_rule_status, validation_report_markdown, validation_report_text,
)

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _run(store, agent, cohort, when, failed, model="groq/openai/gpt-oss-20b", task="t1", infra=None, q4=False):
    obs = store.record_observation(agent, 50.0 - (10 if failed else 0), "Conditional", model_version=model,
                                   genome_hash=f"{agent}-{model}-{task}")
    store.record_evidence(obs, "runtime", "execution", "fail" if failed else "ok", "Q1", source_reference=f"e{obs}")
    pred = store.record_prediction(obs, "runtime_failure", frozen_at=when, cohort_type=cohort,
                                   task_version=f"{cohort}/{task}")
    after = when + timedelta(minutes=1)
    if infra:
        store.record_outcome(pred, "runtime", "infrastructure_error", True, observed_at=after,
                             details=f"error_class={infra}", source_reference=f"i{obs}")
    else:
        store.record_outcome(pred, "runtime", "execution_error", failed, observed_at=after, source_reference=f"o{obs}")
    if q4:
        store.record_outcome(pred, "ext", "execution_error", failed, observed_at=after, quality_level="Q4",
                             source_reference=f"q{obs}")
    return pred


def _store():
    store = EvidenceStore(":memory:")
    store.register_donor("runtime", "execution", "Runtime", "runtime")
    store.register_donor("ext", "outcome", "External", "external_system")
    for i in range(12):  # natural: 12 прогонов, два режима (до и после смены условий)
        model = "groq/openai/gpt-oss-20b" if i < 6 else "groq/qwen/qwen3.8-27b"
        _run(store, f"a{i % 3}", "natural", T0 + timedelta(hours=i), failed=i % 4 == 0, model=model,
             task="old" if i < 6 else "new", q4=i == 11)
    _run(store, "a0", "natural", T0 + timedelta(hours=20), failed=True, infra="model_unavailable")
    _run(store, "a1", "natural", T0 + timedelta(hours=21), failed=True, infra="rate_limit")
    for i in range(4):  # stress_task: 4 прогона, два сценария
        _run(store, f"a{i % 3}", "stress_task", T0 + timedelta(hours=30 + i), failed=i == 0,
             task="trap-a" if i < 2 else "trap-b")
    _run(store, "a2", "stress_task", T0 + timedelta(hours=40), failed=True, infra="model_unavailable")
    return store


def test_cohort_summary_is_scoped_to_cohort_and_counts_exclusions_by_class():
    store = _store()
    natural = cohort_summary(store)
    stress = cohort_summary(store, cohort_types=["stress_task"])
    assert (natural["runs"], natural["excluded_runs"]) == (14, 2)
    assert natural["excluded_by_class"] == {"model_unavailable": 1, "rate_limit": 1}
    assert (stress["runs"], stress["excluded_runs"], stress["excluded_by_class"]) == (5, 1, {"model_unavailable": 1})
    assert natural["evidence_by_quality"]["Q1"] == 14 and stress["evidence_by_quality"]["Q1"] == 5
    assert natural["q4_outcomes"] == 1 and stress["q4_outcomes"] == 0
    assert stress["cohort_types"] == ["stress_task"] and stress["agents"] == 3
    assert cohort_summary(store, cohort_types="all")["runs"] == 19


def test_since_filters_validate_summary_and_scorecard():
    store = _store()
    cutoff = (T0 + timedelta(hours=6)).isoformat()
    assert validate(store, target="runtime_failure").n_pairs == 12
    late = validate(store, target="runtime_failure", since=cutoff)
    assert late.n_pairs == 6 and late.filters["since"] == cutoff
    assert set(late.by_model) == {"groq/qwen/qwen3.8-27b"}
    assert cohort_summary(store, since=cutoff)["runs"] == 8  # 6 новых и 2 исключённых позже
    rows = {r.metric: r for r in accumulation_scorecard(store, since=cutoff)}
    assert rows["observations"].current == 8
    # смещение часового пояса учитывается: тот же момент в +03:00
    shifted = (T0 + timedelta(hours=6)).astimezone(timezone(timedelta(hours=3))).isoformat()
    assert {r.metric: r for r in accumulation_scorecard(store, since=shifted)}["observations"].current == 8


def test_breakdown_by_condition_and_model():
    report = validate(_store(), target="runtime_failure")
    assert report.by_condition == {
        "natural/new": {"pairs": 6, "events": 1, "rate": 0.1667},
        "natural/old": {"pairs": 6, "events": 2, "rate": 0.3333},
    }
    assert report.by_model["groq/openai/gpt-oss-20b"]["pairs"] == 6
    text = validation_report_text(report)
    assert "По условиям (событий/пар): natural/new 1/6; natural/old 2/6" in text
    assert "[рано" not in text  # правило 5.4 только для цели стресс-когорты


def test_scenario_rule_status():
    n = SCENARIO_RETIREMENT["min_runs"]
    assert scenario_rule_status(n - 1, 0).startswith("рано")
    assert scenario_rule_status(n, 1) == "заменить"        # 2% < 5%
    assert scenario_rule_status(n, 10) == "различает"
    assert scenario_rule_status(n, n) == "заменить"        # 100% > 95%


def test_markdown_report_scoped_with_whole_base_and_q4_sections():
    store = _store()
    stress = {"runtime_failure": validate(store, target="runtime_failure", cohort_types=["stress_task"])}
    md = validation_report_markdown(store.evidence_profile(), stress, store.verify_prediction_integrity(),
                                    cohort_summary(store, cohort_types=["stress_task"]))
    assert "## Объём выборки отчёта" in md and "- прогонов 5, из них исключено" in md
    assert "model_unavailable 1" in md
    assert "## Вся база (для контекста)" in md and "наблюдений в базе: 19" in md
    assert "## Q4: внешнее подтверждение" in md and "prizolov-sports-ai" in md
    natural = {"runtime_failure": validate(store, target="runtime_failure")}
    md_natural = validation_report_markdown(store.evidence_profile(), natural, None, cohort_summary(store))
    assert "- прогонов 14," in md_natural and "исходов Q4 в выборке: 1" in md_natural
    assert md != md_natural


def test_stress_report_shows_rule_status_per_scenario():
    store = _store()
    report = validate(store, target="task_failure", cohort_types=["stress_task"])
    assert report.n_pairs == 0  # в фикстуре stress_task только runtime_failure
    runtime = validate(store, target="runtime_failure", cohort_types=["stress_task"])
    md = validation_report_markdown(store.evidence_profile(), {"runtime_failure": runtime})
    assert "Правило 5.4" not in md  # цель stress_task не runtime_failure
    store2 = EvidenceStore(":memory:")
    store2.register_donor("runtime", "execution", "Runtime", "runtime")
    for i in range(3):
        obs = store2.record_observation(f"a{i}", 50.0, "Conditional")
        pred = store2.record_prediction(obs, "task_failure", frozen_at=T0 + timedelta(hours=i),
                                        cohort_type="stress_task", task_version="stress_task/trap-a/distractor")
        store2.record_outcome(pred, "runtime", "task_failure", False, observed_at=T0 + timedelta(hours=i, minutes=1))
    report = validate(store2, target="task_failure", cohort_types=["stress_task"])
    md = validation_report_markdown(store2.evidence_profile(), {"task_failure": report})
    assert "| stress_task/trap-a/distractor | 3 | 0 | 0.0 | рано (3 < 50) |" in md


def test_cli_validate_since_and_cohort_summary_in_report_and_json():
    from agenomics.cli import main
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "e.db")
        store = EvidenceStore(db)
        store.register_donor("runtime", "execution", "Runtime", "runtime")
        store.register_donor("ext", "outcome", "External", "external_system")
        for i in range(4):
            _run(store, f"a{i}", "stress_task", T0 + timedelta(hours=i), failed=i == 0)
        store.close()
        report = os.path.join(tmp, "r.md")
        out = StringIO()
        with redirect_stdout(out):
            assert main(["validate", db, "--cohort-type", "stress_task", "--report", report]) == 0
        assert "Выборка отчёта (когорты stress_task" in out.getvalue()
        assert "## Объём выборки отчёта" in open(report, encoding="utf-8").read()
        out = StringIO()
        with redirect_stdout(out):
            assert main(["validate", db, "--cohort-type", "stress_task", "--since",
                         (T0 + timedelta(hours=2)).isoformat(), "--json"]) == 0
        data = json.loads(out.getvalue())
        assert data["cohort_summary"]["runs"] == 2 and data["runtime_failure"]["n_pairs"] == 2
        out = StringIO()
        with redirect_stdout(out):
            assert main(["scorecard", db, "--cohort-type", "stress_task", "--since",
                         (T0 + timedelta(hours=2)).isoformat(), "--json"]) == 0
        assert next(r for r in json.loads(out.getvalue()) if r["metric"] == "observations")["current"] == 2
