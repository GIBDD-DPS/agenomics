"""Тесты полного пайплайна capture_log_v2 -> genome_from_capture -> EvidenceStore."""

import sys
sys.path.insert(0, ".")

from agenomics import EvidenceStore
from full_pipeline import run_framework_and_record, _HISTORY
from genome_from_capture import _detect_leaked_secrets, derive_genome_from_capture


def test_secret_detection_openai_key():
    log = 'api_key: sk-proj-abcdefghijklmnopqrstuvwxyz123456'
    assert "openai_style_key" in _detect_leaked_secrets(log)


def test_secret_detection_bearer_token():
    log = 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234567890'
    assert "bearer_token" in _detect_leaked_secrets(log)


def test_secret_detection_json_format():
    log = '{"api_key": "sk-1234567890abcdefghijklmnop"}'
    found = _detect_leaked_secrets(log)
    assert "openai_style_key" in found
    assert "generic_api_key_assignment" in found


def test_no_false_positive_on_clean_log():
    log = "INFO: Task completed successfully\nDEBUG: Processing item 42"
    assert _detect_leaked_secrets(log) == []


def test_derived_genome_leaves_bias_control_none():
    """Ключевая проверка честности: bias_control НЕ должен подставляться,
    его нельзя вывести из лога выполнения."""
    result = derive_genome_from_capture("x", "some log", domain="content", autonomy="advisory")
    assert result.genome.bias_control is None
    assert result.genome.transparency is None


def test_derived_genome_has_ledger_true():
    result = derive_genome_from_capture("x", "log", domain="content", autonomy="advisory")
    assert result.genome.has_ledger is True


def test_predictability_requires_three_runs():
    result_1run = derive_genome_from_capture(
        "x", "log", framework_history_statuses=["success"], framework_history_durations=[1.0]
    )
    assert result_1run.genome.drift_rate is None

    result_3runs = derive_genome_from_capture(
        "x", "log",
        framework_history_statuses=["success", "error", "success"],
        framework_history_durations=[1.0, 1.5, 0.9],
    )
    assert result_3runs.genome.drift_rate is not None


def test_full_pipeline_records_observation():
    _HISTORY.clear()
    store = EvidenceStore(":memory:")

    def clean_run():
        print("OK")

    summary = run_framework_and_record("test-fw", clean_run, store, domain="content", print_report=False)
    assert summary["status"] == "success"
    assert store.count_observations("test-fw") == 1
    obs = store.get_observations("test-fw")[0]
    assert obs.genome_hash is not None
    store.close()


def test_full_pipeline_crash_becomes_confirmed_incident():
    _HISTORY.clear()
    store = EvidenceStore(":memory:")

    def crashing_run():
        raise ValueError("boom")

    summary = run_framework_and_record("crash-fw", crashing_run, store, domain="content", print_report=False)
    assert summary["status"] == "error"
    obs = store.get_observations("crash-fw")[0]
    assert len(obs.incidents) == 1
    assert obs.incidents[0]["confirmed"] is True
    assert obs.incidents[0]["severity"] == "severe"
    store.close()


def test_full_pipeline_leak_becomes_data_leak_incident():
    _HISTORY.clear()
    store = EvidenceStore(":memory:")

    def leaking_run():
        print('token: Bearer abcdefghijklmnopqrstuvwxyz1234567890')

    run_framework_and_record("leak-fw", leaking_run, store, domain="content", print_report=False)
    obs = store.get_observations("leak-fw")[0]
    assert any(inc["category"] == "data_leak" for inc in obs.incidents)
    store.close()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"OK: {t.__name__}")
    print(f"\n{passed}/{len(tests)} passed")
