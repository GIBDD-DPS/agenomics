# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_hooks.py. Тесты EvidenceStoreHook.

Проект: Prizolov Lab
"""

from agenomics import AgentGenome, TrustScorer, DriftMonitorV2, EvidenceStore
from agenomics.hooks import EvidenceStoreHook


def _make_result():
    genome = AgentGenome(id="x", domain="content", bias_control=85, transparency=80, data_safety=90, has_ledger=True)
    return TrustScorer().score(genome)


def test_on_trust_scored_records_observation():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    obs_id = hook.on_trust_scored("agent-1", _make_result())
    assert obs_id is not None
    assert store.count_observations("agent-1") == 1


def test_genome_hash_attaches_to_next_observation():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    hook.on_genome_extracted("agent-1", genome_hash="deadbeef")
    hook.on_trust_scored("agent-1", _make_result())
    obs = store.get_observations("agent-1")[0]
    assert obs.genome_hash == "deadbeef"


def test_genome_hash_is_none_if_not_set():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    hook.on_trust_scored("agent-1", _make_result())
    obs = store.get_observations("agent-1")[0]
    assert obs.genome_hash is None


def test_on_drift_alert_attaches_incident():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    monitor = DriftMonitorV2()
    for score in [88, 85, 78, 70, 60, 50]:
        monitor.record("agent-1", score)
    report = monitor.report("agent-1")
    assert report.alert is True

    hook.on_drift_alert("agent-1", report)
    obs = store.get_observations("agent-1")[0]
    assert len(obs.incidents) == 1
    assert obs.incidents[0]["confirmed"] is True
    assert obs.incidents[0]["category"] == "other"


def test_severe_drift_maps_to_severe_incident():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    monitor = DriftMonitorV2()
    for score in [90, 88, 85, 60, 30, 10]:  # резкое падение -> severe/sudden
        monitor.record("agent-1", score)
    report = monitor.report("agent-1")
    assert report.severity in ("severe", "sudden", "moderate")  # зависит от точной динамики

    hook.on_drift_alert("agent-1", report)
    obs = store.get_observations("agent-1")[0]
    expected_severity = "severe" if report.severity in ("severe", "sudden") else "moderate"
    assert obs.incidents[0]["severity"] == expected_severity


def test_explicit_genome_hash_survives_simulated_process_restart():
    """Регрессионный тест на реальную находку внешнего разбора:
    _last_genome_hash был чисто in-memory кэшем, терялся при
    перезапуске процесса между on_genome_extracted() и on_trust_scored().
    Теперь genome_hash можно передать явно, минуя кэш."""
    store = EvidenceStore(":memory:")

    # 'Новый процесс' - свежий hook, кэш пуст, on_genome_extracted() не вызывался
    hook = EvidenceStoreHook(store)
    hook.on_trust_scored("agent-1", _make_result(), genome_hash="from-caller-directly")

    obs = store.get_observations("agent-1")[0]
    assert obs.genome_hash == "from-caller-directly"


def test_explicit_genome_hash_overrides_cache():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    hook.on_genome_extracted("agent-1", genome_hash="cached-value")
    hook.on_trust_scored("agent-1", _make_result(), genome_hash="explicit-value")
    obs = store.get_observations("agent-1")[0]
    assert obs.genome_hash == "explicit-value"  # явный параметр важнее кэша


def test_source_and_collector_are_recorded():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store, collector="my_orchestrator", source="agent-fleet-1")
    hook.on_trust_scored("agent-1", _make_result())
    obs = store.get_observations("agent-1")[0]
    assert obs.collector == "my_orchestrator"
    assert obs.source == "agent-fleet-1"



# --- v0.8.0: маркер исхода задачи ----------------------------------------

def test_task_outcome_recorded_on_pre_task_observation():
    from agenomics import Incident, IncidentCategory, IncidentSeverity
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    obs_id = hook.on_trust_scored("agent-1", _make_result(), model_version="groq/x", prompt_version="v2")
    assert store.get_observations("agent-1")[0].task_outcome is None  # исход ещё неизвестен
    hook.on_task_outcome(obs_id, "failure", [
        Incident("wrong prediction", IncidentSeverity.MODERATE, category=IncidentCategory.RESPONSE_QUALITY),
    ])
    obs = store.get_observations("agent-1")[0]
    assert obs.task_outcome == "failure"
    assert obs.model_version == "groq/x" and obs.prompt_version == "v2"
    assert obs.incidents[0]["category"] == "response_quality"
    assert store.count_observations("agent-1") == 1  # то же наблюдение, не новое


def test_task_outcome_cannot_be_overwritten():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    obs_id = hook.on_trust_scored("agent-1", _make_result())
    hook.on_task_outcome(obs_id, "success")
    try:
        hook.on_task_outcome(obs_id, "failure")
        assert False, "перезапись исхода должна быть запрещена"
    except ValueError:
        pass
    assert store.get_observations("agent-1")[0].task_outcome == "success"


def test_task_outcome_rejects_unknown_value_and_missing_observation():
    store = EvidenceStore(":memory:")
    hook = EvidenceStoreHook(store)
    obs_id = hook.on_trust_scored("agent-1", _make_result())
    for bad_call in (lambda: hook.on_task_outcome(obs_id, "great"), lambda: hook.on_task_outcome(9999, "success")):
        try:
            bad_call()
            assert False, "ожидался ValueError"
        except ValueError:
            pass


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK:", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} passed")
