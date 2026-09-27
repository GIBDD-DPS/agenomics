# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_evidence_graph.py. Доноры, доказательства, предсказания и исходы (v0.9.0).

Проект: Prizolov Lab
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from agenomics import EvidenceStore, AEP_SCHEMA_VERSION


def _expect_value_error(fn):
    try:
        fn()
    except ValueError:
        return
    assert False, "ожидался ValueError"


def _store_with_observation(agent_id="agent-1", score=61.4):
    store = EvidenceStore(":memory:")
    obs_id = store.record_observation(agent_id, score, "Conditional", genome_hash="g1")
    return store, obs_id


def _register_judges(store):
    store.register_donor("gpt-judge-a", "judge", "GPT Judge A", "openai_llm", provider="OpenAI", model="gpt-x")
    store.register_donor("gpt-judge-b", "judge", "GPT Judge B", "openai_llm", provider="OpenAI", model="gpt-x")
    store.register_donor("claude-judge", "judge", "Claude Judge", "anthropic_llm", provider="Anthropic")
    store.register_donor("runtime", "execution", "Runtime Monitor", "runtime")
    store.register_donor("human-1", "human", "Security engineer", "human")


# --- Donors ----------------------------------------------------------------

def test_register_donor_is_idempotent_for_same_fields():
    store = EvidenceStore(":memory:")
    first = store.register_donor("runtime", "execution", "Runtime Monitor", "runtime", version="1.0")
    again = store.register_donor("runtime", "execution", "Runtime Monitor", "runtime", version="1.0")
    assert first == again
    assert len(store.list_donors()) == 1


def test_changed_donor_must_use_new_id():
    store = EvidenceStore(":memory:")
    store.register_donor("judge", "judge", "Judge", "openai_llm", model="gpt-x")
    _expect_value_error(lambda: store.register_donor("judge", "judge", "Judge", "openai_llm", model="gpt-y"))


def test_donor_validation():
    store = EvidenceStore(":memory:")
    _expect_value_error(lambda: store.register_donor("x", "oracle", "X", "g"))
    _expect_value_error(lambda: store.register_donor("x", "judge", "X", ""))


# --- Evidence --------------------------------------------------------------

def test_evidence_carries_independence_group_from_donor():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    store.record_evidence(obs_id, "gpt-judge-a", "behavioral_evaluation", "safe", "Q3", confidence=0.87)
    evidence = store.get_evidence(observation_id=obs_id)
    assert evidence[0].independence_group == "openai_llm"
    assert evidence[0].confidence == 0.87


def test_contradicting_evidence_is_kept():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    store.register_donor("scanner", "security", "Secret scanner", "regex_scanner")
    store.record_evidence(obs_id, "gpt-judge-a", "behavioral_evaluation", "safe", "Q3")
    store.record_evidence(obs_id, "scanner", "secret_scan", "leak:api_key", "Q2")
    findings = {e.donor_id: e.finding for e in store.get_evidence(observation_id=obs_id)}
    assert findings == {"gpt-judge-a": "safe", "scanner": "leak:api_key"}


def test_evidence_validation():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    _expect_value_error(lambda: store.record_evidence(obs_id, "unknown", "t", "f", "Q2"))
    _expect_value_error(lambda: store.record_evidence(999, "runtime", "t", "f", "Q2"))
    _expect_value_error(lambda: store.record_evidence(obs_id, "runtime", "t", "f", "Q9"))
    _expect_value_error(lambda: store.record_evidence(obs_id, "runtime", "t", "f", "Q1", confidence=1.5))


# --- Predictions and outcomes ----------------------------------------------

def test_prediction_freezes_score_of_observation():
    store, obs_id = _store_with_observation(score=61.4)
    pred_id = store.record_prediction(obs_id, target="behavioral_incident", horizon="next_execution")
    prediction = store.get_predictions("agent-1")[0]
    assert prediction.id == pred_id
    assert prediction.trust_score == 61.4
    assert prediction.target == "behavioral_incident"
    assert prediction.outcomes == []


def test_outcome_must_be_observed_after_freeze():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    frozen = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
    pred_id = store.record_prediction(obs_id, "behavioral_incident", frozen_at=frozen)
    _expect_value_error(lambda: store.record_outcome(pred_id, "runtime", "behavioral_incident", True, observed_at=frozen))
    _expect_value_error(lambda: store.record_outcome(
        pred_id, "runtime", "behavioral_incident", True, observed_at=frozen - timedelta(minutes=1)))
    store.record_outcome(pred_id, "runtime", "behavioral_incident", True, observed_at=frozen + timedelta(minutes=3))
    assert store.get_predictions()[0].outcomes[0].occurred is True


def test_naive_timestamps_are_treated_as_utc():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    pred_id = store.record_prediction(obs_id, "incident", frozen_at=datetime(2026, 9, 24, 9, 0))
    store.record_outcome(pred_id, "runtime", "incident", False, observed_at=datetime(2026, 9, 24, 9, 1))
    assert store.get_predictions()[0].outcomes[0].occurred is False


def test_multiple_outcomes_from_different_donors_are_kept():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    pred_id = store.record_prediction(obs_id, "unsafe_action")
    store.record_outcome(pred_id, "claude-judge", "unsafe_action", False)
    store.record_outcome(pred_id, "human-1", "unsafe_action", True, verification="human", details="x" * 500)
    outcomes = store.get_predictions()[0].outcomes
    assert [(o.donor_id, o.occurred) for o in outcomes] == [("claude-judge", False), ("human-1", True)]
    assert outcomes[1].independence_group == "human"
    assert len(outcomes[1].details) == 200


def test_outcome_validation():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    pred_id = store.record_prediction(obs_id, "incident")
    _expect_value_error(lambda: store.record_outcome(999, "runtime", "incident", True))
    _expect_value_error(lambda: store.record_outcome(pred_id, "unknown", "incident", True))
    _expect_value_error(lambda: store.record_outcome(pred_id, "runtime", "incident", True, verification="vibes"))
    _expect_value_error(lambda: store.record_prediction(999, "incident"))


# --- record_execution ------------------------------------------------------

def test_record_execution_is_write_once():
    store, obs_id = _store_with_observation()
    store.record_execution(obs_id, "error", 2.5)
    obs = store.get_observations("agent-1")[0]
    assert obs.execution_status == "error" and obs.duration_seconds == 2.5
    _expect_value_error(lambda: store.record_execution(obs_id, "success", 1.0))
    _expect_value_error(lambda: store.record_execution(obs_id + 1, "success"))
    store2, obs2 = _store_with_observation()
    _expect_value_error(lambda: store2.record_execution(obs2, "crashed"))


# --- Profile ---------------------------------------------------------------

def test_profile_separates_volume_from_independence():
    """Пример из разбора: 100 оценок одного GPT-судьи это не 100
    независимых подтверждений."""
    store = EvidenceStore(":memory:")
    _register_judges(store)
    for _ in range(100):
        obs_id = store.record_observation("agent-x", 70.0, "Conditional", genome_hash="g1")
        store.record_evidence(obs_id, "gpt-judge-a", "behavioral_evaluation", "safe", "Q3")
    one_source = store.evidence_profile("agent-x")
    assert one_source.n_evidence == 100
    assert one_source.n_donors == 1
    assert one_source.n_independence_groups == 1
    assert one_source.n_genomes == 1

    obs_id = store.record_observation("agent-y", 70.0, "Conditional", genome_hash="g2")
    for donor, quality in (("gpt-judge-a", "Q3"), ("gpt-judge-b", "Q3"), ("claude-judge", "Q3"),
                           ("runtime", "Q1"), ("human-1", "Q4")):
        store.record_evidence(obs_id, donor, "evaluation", "safe", quality)
    diverse = store.evidence_profile("agent-y")
    assert diverse.n_donors == 5
    assert diverse.n_independence_groups == 4  # два GPT-судьи в одной группе
    assert diverse.independence_groups["openai_llm"] == 2
    assert diverse.evidence_by_quality == {"Q0": 0, "Q1": 1, "Q2": 0, "Q3": 3, "Q4": 1}


def test_profile_counts_predictions_and_verified_outcomes():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    p1 = store.record_prediction(obs_id, "incident")
    store.record_prediction(obs_id, "incident", horizon="next_week")
    store.record_outcome(p1, "runtime", "incident", False)
    store.record_outcome(p1, "human-1", "incident", False, verification="ground_truth")
    profile = store.evidence_profile()
    assert profile.n_predictions == 2
    assert profile.n_predictions_with_outcome == 1
    assert profile.n_verified_outcomes == 1
    assert profile.n_agents == 1


# --- Persistence, migration, export ----------------------------------------

def test_graph_survives_reopen_and_old_files_get_new_tables():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "old.db")
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, timestamp TEXT NOT NULL,
                declared_score REAL NOT NULL, declared_label TEXT NOT NULL, declared_confidence TEXT,
                genome_hash TEXT, genome_version TEXT, trust_model_version TEXT, evaluation_period TEXT,
                request_count INTEGER, schema_version TEXT, collector TEXT, source TEXT
            );
            CREATE TABLE incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT, observation_id INTEGER NOT NULL, severity TEXT NOT NULL,
                description TEXT, category TEXT, source TEXT, confirmed INTEGER, resolution TEXT
            );
            """
        )
        conn.close()

        store = EvidenceStore(db_path)
        store.register_donor("runtime", "execution", "Runtime Monitor", "runtime")
        obs_id = store.record_observation("a", 50.0, "Conditional")
        pred_id = store.record_prediction(obs_id, "incident")
        store.record_outcome(pred_id, "runtime", "incident", True)
        store.close()

        reopened = EvidenceStore(db_path)
        assert reopened.get_predictions("a")[0].outcomes[0].occurred is True
        assert reopened.get_observations("a")[0].schema_version == AEP_SCHEMA_VERSION == "1.2"
        reopened.close()


def test_export_evidence_graph_json():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    store.record_evidence(obs_id, "runtime", "execution", "success", "Q1")
    pred_id = store.record_prediction(obs_id, "incident")
    store.record_outcome(pred_id, "runtime", "incident", False)
    with tempfile.TemporaryDirectory() as tmp:
        with open(store.export_evidence_graph_json(os.path.join(tmp, "graph.json")), encoding="utf-8") as f:
            data = json.load(f)
    assert {d["donor_id"] for d in data["donors"]} >= {"runtime", "gpt-judge-a"}
    assert data["evidence"][0]["independence_group"] == "runtime"
    assert data["predictions"][0]["outcomes"][0]["donor_id"] == "runtime"


def test_default_outcome_time_equal_to_freeze_is_accepted():
    """Разрешение часов: вызов record_outcome() сразу после
    record_prediction() может получить то же время."""
    from unittest import mock
    import agenomics.evidence_graph as graph
    store, obs_id = _store_with_observation()
    _register_judges(store)
    fixed = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
    with mock.patch.object(graph, "_now", return_value=fixed):
        pred_id = store.record_prediction(obs_id, "incident")
        store.record_outcome(pred_id, "runtime", "incident", False)
    assert len(store.get_predictions()[0].outcomes) == 1


# --- v0.9.6: снимок, неизменяемость, класс и качество исхода, отпечатки -------

def _v095_database(path):
    """База в схеме 0.9.5: графовые таблицы без новых колонок, с повтором
    доказательства и исходом неизвестного типа."""
    from agenomics.evidence import _SCHEMA_SQL
    from agenomics.evidence_graph import GRAPH_SCHEMA_SQL
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA_SQL)
    conn.executescript(GRAPH_SCHEMA_SQL)
    now = "2026-09-25T10:00:00+00:00"
    conn.execute("INSERT INTO donors VALUES ('runtime','execution','Runtime','runtime',NULL,NULL,NULL,'{}',?)", (now,))
    conn.execute(
        "INSERT INTO observations (agent_id, declared_score, declared_label, timestamp, trust_model_version) "
        "VALUES ('a', 50.0, 'Conditional', ?, '0.9.5')", (now,),
    )
    for _ in range(2):  # один и тот же сигнал записан дважды
        conn.execute("INSERT INTO evidence (observation_id, donor_id, evidence_type, finding, quality_level, "
                     "created_at) VALUES (1, 'runtime', 'execution', 'success', 'Q1', ?)", (now,))
    conn.execute("INSERT INTO predictions (observation_id, agent_id, trust_score, target, horizon, frozen_at) "
                 "VALUES (1, 'a', 50.0, 'runtime_failure', 'next_execution', ?)", (now,))
    later = "2026-09-25T10:00:05+00:00"
    conn.execute("INSERT INTO outcomes (prediction_id, donor_id, outcome_type, occurred, verification, observed_at) "
                 "VALUES (1, 'runtime', 'execution_error', 0, 'automated', ?)", (later,))
    conn.execute("INSERT INTO outcomes (prediction_id, donor_id, outcome_type, occurred, verification, observed_at) "
                 "VALUES (1, 'runtime', 'custom_signal', 1, 'automated', ?)", (later,))
    conn.commit()
    conn.close()


def test_v095_database_is_migrated_without_losing_rows():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "old.db")
        _v095_database(path)
        store = EvidenceStore(path)
        outcomes = store.get_predictions()[0].outcomes
        assert [(o.outcome_type, o.occurred, o.outcome_class, o.quality_level) for o in outcomes] == [
            ("execution_error", False, "RUNTIME", "Q1"), ("custom_signal", True, None, "Q1")]
        profile = store.evidence_profile()
        assert profile.n_evidence == 2 and profile.n_duplicate_evidence == 1
        assert profile.n_outcomes_without_class == 1
        assert store.verify_prediction_integrity() == {"checked": 0, "without_snapshot": 1, "violations": []}
        triggers = {r[0] for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        assert {"predictions_no_update", "outcomes_no_delete", "evidence_no_update"} <= triggers
        store.close()
        store = EvidenceStore(path)  # повторное открытие ничего не меняет
        assert store.evidence_profile().n_duplicate_evidence == 1
        store.close()


def test_graph_tables_are_append_only():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    store.record_evidence(obs_id, "runtime", "execution", "success", "Q1")
    pred = store.record_prediction(obs_id, "runtime_failure")
    store.record_outcome(pred, "runtime", "execution_error", False)
    for sql in ("UPDATE predictions SET trust_score = 99", "DELETE FROM predictions",
                "UPDATE outcomes SET occurred = 1", "DELETE FROM outcomes",
                "UPDATE evidence SET finding = 'x'", "DELETE FROM evidence"):
        try:
            store._conn.execute(sql)
            assert False, f"{sql} должен быть запрещён"
        except sqlite3.DatabaseError as e:
            assert "append-only" in str(e)


def test_prediction_snapshot_matches_observation_and_detects_tampering():
    store = EvidenceStore(":memory:")
    obs_id = store.record_observation("a", 47.0, "Conditional", genome_hash="g1", trust_model_version="0.9.6",
                                      model_version="groq/m", prompt_version="task-v2", framework_version="1.0")
    pred = store.record_prediction(obs_id, "task_failure", task_version="task-v2", environment_id="local")
    snapshot = store.get_predictions()[0].snapshot
    assert snapshot["trust_score"] == 47.0 and snapshot["genome_hash"] == "g1"
    assert snapshot["model_version"] == "groq/m" and snapshot["environment_id"] == "local"
    assert store.verify_prediction_integrity() == {"checked": 1, "without_snapshot": 0, "violations": []}
    # подмена в обход API: снимок перестаёт сходиться с хэшем
    store._conn.execute("DROP TRIGGER predictions_no_update")
    store._conn.execute("UPDATE predictions SET snapshot_json = replace(snapshot_json, '47.0', '90.0') WHERE id = ?",
                        (pred,))
    store._conn.execute("UPDATE predictions SET trust_score = 90.0 WHERE id = ?", (pred,))
    problems = store.verify_prediction_integrity()["violations"]
    assert problems == [{"prediction_id": pred, "problem": "snapshot_sha256"}]
    _expect_value_error(lambda: store.record_prediction(obs_id, "task_failure", task_version="task-v2"))


def test_repeated_evidence_and_outcome_are_not_counted_twice():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    first = store.record_evidence(obs_id, "runtime", "execution", "success", "Q1", source_reference="run-1")
    assert store.record_evidence(obs_id, "runtime", "execution", "success", "Q1", source_reference="run-1") == first
    assert store.record_evidence(obs_id, "runtime", "execution", "success", "Q1", source_reference="run-2") != first
    pred = store.record_prediction(obs_id, "runtime_failure")
    o1 = store.record_outcome(pred, "runtime", "execution_error", False)
    assert store.record_outcome(pred, "runtime", "execution_error", False) == o1
    assert len(store.get_predictions()[0].outcomes) == 1


def test_outcome_class_and_quality():
    store, obs_id = _store_with_observation()
    _register_judges(store)
    store.record_evidence(obs_id, "claude-judge", "task_check", "fail", "Q3")
    pred = store.record_prediction(obs_id, "task_failure")
    store.record_outcome(pred, "claude-judge", "task_failure", True)
    store.record_outcome(pred, "human-1", "wrong_tone", True, outcome_class="BEHAVIORAL", quality_level="Q4",
                         verification="human")
    outcomes = store.get_predictions()[0].outcomes
    assert [(o.outcome_class, o.quality_level) for o in outcomes] == [("TASK", "Q3"), ("BEHAVIORAL", "Q4")]
    _expect_value_error(lambda: store.record_outcome(pred, "runtime", "x", True, outcome_class="MISC"))
    _expect_value_error(lambda: store.record_outcome(pred, "runtime", "x", True, quality_level="Q9"))


def test_duplicate_predictions_in_old_database_block_unique_index_but_are_counted():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "old.db")
        _v095_database(path)
        conn = sqlite3.connect(path)
        conn.execute("INSERT INTO predictions (observation_id, agent_id, trust_score, target, horizon, frozen_at) "
                     "VALUES (1, 'a', 50.0, 'runtime_failure', 'next_execution', '2026-09-25T10:00:00+00:00')")
        conn.commit()
        conn.close()
        store = EvidenceStore(path)
        assert store.evidence_profile().n_duplicate_predictions == 1
        indexes = {r[0] for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert "ux_predictions_obs_target" not in indexes
        store.close()
