"""
test_evidence.py — тесты Evidence Store (v0.7.0).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.7.0
"""

import json
import os
import tempfile

from agenomics import Incident, IncidentSeverity
from agenomics.evaluation import RealWorldEvaluationLayer
from agenomics.evidence import EvidenceStore, replay_into_evaluation_layer


def test_record_and_count_observations():
    store = EvidenceStore(":memory:")
    store.record_observation("agent-a", 80.0, "Trusted")
    store.record_observation("agent-a", 85.0, "Trusted")
    store.record_observation("agent-b", 40.0, "High Risk")
    assert store.count_observations("agent-a") == 2
    assert store.count_observations("agent-b") == 1
    assert store.count_observations() == 3


def test_incidents_are_persisted_and_retrieved():
    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-a", 60.0, "Conditional",
        incidents=[Incident("утечка", IncidentSeverity.SEVERE), Incident("мелочь", IncidentSeverity.MINOR)],
    )
    obs = store.get_observations("agent-a")
    assert len(obs) == 1
    assert len(obs[0].incidents) == 2
    severities = {inc["severity"] for inc in obs[0].incidents}
    assert severities == {"severe", "minor"}


def test_genome_hash_and_version_are_stored():
    store = EvidenceStore(":memory:")
    store.record_observation("agent-a", 80.0, "Trusted", genome_hash="deadbeef", agenomics_version="9.9.9")
    obs = store.get_observations("agent-a")[0]
    assert obs.genome_hash == "deadbeef"
    assert obs.agenomics_version == "9.9.9"


def test_agenomics_version_defaults_to_current_package_version():
    import agenomics
    store = EvidenceStore(":memory:")
    store.record_observation("agent-a", 80.0, "Trusted")
    obs = store.get_observations("agent-a")[0]
    assert obs.agenomics_version == agenomics.__version__


def test_export_json_roundtrip():
    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-a", 72.5, "Conditional",
        incidents=[Incident("test", IncidentSeverity.MODERATE)],
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.json")
        store.export_json(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["declared_score"] == 72.5
        assert data[0]["incidents"][0]["severity"] == "moderate"


def test_export_csv_has_expected_columns_and_row_count():
    store = EvidenceStore(":memory:")
    store.record_observation("agent-a", 80.0, "Trusted")
    store.record_observation("agent-a", 82.0, "Trusted", incidents=[Incident("x", IncidentSeverity.SEVERE)])
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.csv")
        store.export_csv(path)
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 3  # header + 2 rows
        assert "n_severe" in lines[0]


def test_persistence_survives_reconnect_to_same_file():
    """Ключевое свойство Evidence Store: данные должны переживать
    закрытие и повторное открытие соединения с тем же файлом — то,
    чего RealWorldEvaluationLayer сам по себе не умеет."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "persist.db")

        store1 = EvidenceStore(db_path)
        store1.record_observation("agent-a", 80.0, "Trusted")
        store1.close()

        store2 = EvidenceStore(db_path)  # "перезапуск процесса"
        assert store2.count_observations("agent-a") == 1
        store2.close()


def test_replay_into_evaluation_layer_reconstructs_correlation():
    """Полный сценарий: запись -> имитация перезапуска -> воспроизведение
    в свежий RealWorldEvaluationLayer -> корректный расчёт корреляции."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "replay.db")
        store = EvidenceStore(db_path)

        for i in range(12):
            score = 90.0 if i % 2 == 0 else 40.0
            incidents = [] if i % 2 == 0 else [Incident("x", IncidentSeverity.MODERATE)]
            store.record_observation(
                "agent-x", score, "Trusted" if score > 60 else "High Risk",
                declared_confidence="High", incidents=incidents,
            )

        fresh_layer = RealWorldEvaluationLayer(min_observations=10)
        n_replayed = replay_into_evaluation_layer(store, fresh_layer, "agent-x")
        assert n_replayed == 12

        report = fresh_layer.trust_reality_report("agent-x")
        assert report.status == "computed"
        assert report.n_observations == 12
        assert report.correlation < 0  # высокий score -> нет инцидентов, по конструкции теста

        store.close()


def test_context_manager_closes_connection():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "ctx.db")
        with EvidenceStore(db_path) as store:
            store.record_observation("a", 80.0, "Trusted")
            assert store.count_observations() == 1
        # После выхода из контекста соединение закрыто — повторное
        # открытие того же файла должно всё ещё видеть данные.
        store2 = EvidenceStore(db_path)
        assert store2.count_observations() == 1
        store2.close()
