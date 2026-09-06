"""Тесты полного пайплайна capture_log_v2 -> genome_from_capture -> EvidenceStore."""

import sys
sys.path.insert(0, ".")

from agenomics import EvidenceStore
from full_pipeline import run_framework_and_record
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


def test_derived_genome_has_ledger_false_by_default():
    """[v0.7.2, исправление после внешнего разбора] has_ledger больше НЕ
    True по умолчанию: capture_log сам по себе не делает фреймворк
    обладателем настоящего audit trail."""
    result = derive_genome_from_capture("x", "log", domain="content", autonomy="advisory")
    assert result.genome.has_ledger is False


def test_has_ledger_can_be_explicitly_asserted_true():
    result = derive_genome_from_capture("x", "log", domain="content", autonomy="advisory", has_ledger=True)
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
    store = EvidenceStore(":memory:")

    def leaking_run():
        print('token: Bearer abcdefghijklmnopqrstuvwxyz1234567890')

    run_framework_and_record("leak-fw", leaking_run, store, domain="content", print_report=False)
    obs = store.get_observations("leak-fw")[0]
    assert any(inc["category"] == "data_leak" for inc in obs.incidents)
    store.close()


def test_history_persists_across_separate_evidence_store_objects():
    """[v0.7.2, ключевой регрессионный тест] Имитация реального сценария
    GitHub Actions: КАЖДЫЙ вызов run_framework_and_record идёт с НОВЫМ
    объектом EvidenceStore на том же файле (как между отдельными
    процессами). История не должна теряться. Раньше (баг, найденный
    внешним разбором) она хранилась в module-level _HISTORY и терялась
    при каждом новом процессе."""
    import tempfile

    def sometimes_fails():
        import random
        if random.random() < 0.5:
            raise RuntimeError("boom")
        print("ok")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/restart.db"
        for _ in range(5):
            store = EvidenceStore(db_path)  # "новый процесс"
            run_framework_and_record("restart-fw", sometimes_fails, store, domain="content", print_report=False)
            store.close()  # "процесс завершился". Если бы история была в памяти, она бы тут пропала

        final_store = EvidenceStore(db_path)
        observations = final_store.get_observations("restart-fw")
        assert len(observations) == 5
        # Все execution_status должны быть реально сохранены персистентно
        assert all(o.execution_status in ("success", "error") for o in observations)
        final_store.close()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"OK: {t.__name__}")
    print(f"\n{passed}/{len(tests)} passed")
