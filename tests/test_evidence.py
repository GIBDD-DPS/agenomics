# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_evidence.py. Тесты Evidence Store.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
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
    store.record_observation("agent-a", 80.0, "Trusted", genome_hash="deadbeef", trust_model_version="9.9.9")
    obs = store.get_observations("agent-a")[0]
    assert obs.genome_hash == "deadbeef"
    assert obs.trust_model_version == "9.9.9"


def test_agenomics_version_defaults_to_current_package_version():
    import agenomics
    store = EvidenceStore(":memory:")
    store.record_observation("agent-a", 80.0, "Trusted")
    obs = store.get_observations("agent-a")[0]
    assert obs.trust_model_version == agenomics.__version__


def test_agenomics_version_alias_still_works_for_backward_compat():
    """agenomics_version, устаревшее имя параметра, должно
    по-прежнему работать как алиас trust_model_version."""
    store = EvidenceStore(":memory:")
    store.record_observation("agent-a", 80.0, "Trusted", agenomics_version="7.7.7")
    obs = store.get_observations("agent-a")[0]
    assert obs.trust_model_version == "7.7.7"


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
    закрытие и повторное открытие соединения с тем же файлом. То,
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
        # После выхода из контекста соединение закрыто. Повторное
        # открытие того же файла должно всё ещё видеть данные.
        store2 = EvidenceStore(db_path)
        assert store2.count_observations() == 1
        store2.close()


# --- Тесты v0.7.2: execution_status / duration_seconds -----------------

def test_execution_status_and_duration_persisted():
    """Ключевая проверка исправления найденного бага: эти два поля
    должны реально сохраняться и читаться обратно, а не теряться."""
    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-a", 60.0, "Conditional",
        execution_status="error", duration_seconds=1.234,
    )
    obs = store.get_observations("agent-a")[0]
    assert obs.execution_status == "error"
    assert obs.duration_seconds == 1.234


def test_execution_status_defaults_to_none_for_old_callers():
    """Старый код, не знающий про execution_status/duration_seconds,
    не должен падать и не должен получать фиктивные значения."""
    store = EvidenceStore(":memory:")
    store.record_observation("agent-a", 60.0, "Conditional")
    obs = store.get_observations("agent-a")[0]
    assert obs.execution_status is None
    assert obs.duration_seconds is None


def test_history_reconstructable_across_simulated_restarts():
    """Полная имитация найденной проблемы: 5 'запусков' одного и того
    же agent_id через РАЗНЫЕ объекты EvidenceStore (тот же файл), как
    это происходило бы между перезапусками процесса в GitHub Actions.
    После этого история должна реконструироваться ПОЛНОСТЬЮ из файла,
    без единого in-memory словаря."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "restart_sim.db")
        statuses_written = ["success", "error", "success", "success", "error"]
        durations_written = [1.0, 2.5, 0.8, 1.1, 3.0]

        for status, duration in zip(statuses_written, durations_written):
            # Новый объект EvidenceStore каждый раз, имитация нового процесса.
            store = EvidenceStore(db_path)
            store.record_observation(
                "restart-agent", 60.0, "Conditional",
                execution_status=status, duration_seconds=duration,
            )
            store.close()

        # Финальное "новое подключение" реконструирует всю историю.
        final_store = EvidenceStore(db_path)
        observations = final_store.get_observations("restart-agent")
        assert len(observations) == 5
        reconstructed_statuses = [o.execution_status for o in observations]
        reconstructed_durations = [o.duration_seconds for o in observations]
        assert reconstructed_statuses == statuses_written
        assert reconstructed_durations == durations_written
        final_store.close()


# --- Тесты схемы AEP-001 (v0.7.1) --------------------------------------

def test_aep001_observation_fields_stored():
    from agenomics.evidence import AEP_SCHEMA_VERSION

    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-a", 80.0, "Trusted",
        genome_version="v3", evaluation_period="2026-09-01/2026-09-02",
        request_count=1200, collector="sdk", source="prod-cluster-1",
    )
    obs = store.get_observations("agent-a")[0]
    assert obs.genome_version == "v3"
    assert obs.evaluation_period == "2026-09-01/2026-09-02"
    assert obs.request_count == 1200
    assert obs.collector == "sdk"
    assert obs.source == "prod-cluster-1"
    assert obs.schema_version == AEP_SCHEMA_VERSION


def test_aep001_incident_structured_fields_stored():
    from agenomics import Incident, IncidentCategory, IncidentSeverity, IncidentSource

    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-a", 60.0, "Conditional",
        incidents=[Incident(
            description="кратко: жалоба на тон", severity=IncidentSeverity.MODERATE,
            category=IncidentCategory.RESPONSE_QUALITY, source=IncidentSource.SUPPORT_TICKET,
            confirmed=True, resolution="fixed",
        )],
    )
    obs = store.get_observations("agent-a")[0]
    inc = obs.incidents[0]
    assert inc["category"] == "response_quality"
    assert inc["source"] == "support_ticket"
    assert inc["confirmed"] is True
    assert inc["resolution"] == "fixed"


def test_aep001_incident_optional_fields_default_none():
    """Старый способ создания Incident (без полей протокола) не должен
    падать и не должен подставлять фиктивные значения вместо None."""
    from agenomics import Incident, IncidentSeverity

    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-a", 60.0, "Conditional",
        incidents=[Incident("старый стиль", IncidentSeverity.MINOR)],
    )
    inc = store.get_observations("agent-a")[0].incidents[0]
    assert inc["category"] is None
    assert inc["source"] is None
    assert inc["confirmed"] is True  # default Incident.confirmed=True
    assert inc["resolution"] is None


def test_aep001_replay_preserves_structured_incident_fields():
    from agenomics import Incident, IncidentCategory, IncidentSeverity, IncidentSource
    from agenomics.evaluation import RealWorldEvaluationLayer

    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-x", 60.0, "Conditional", declared_confidence="High",
        incidents=[Incident(
            "кратко", IncidentSeverity.SEVERE, category=IncidentCategory.DATA_LEAK,
            source=IncidentSource.AUTOMATED_MONITOR, confirmed=False,
        )],
    )
    layer = RealWorldEvaluationLayer(min_observations=1)
    replay_into_evaluation_layer(store, layer, "agent-x")
    replayed_incident = layer.observations("agent-x")[0].incidents[0]
    assert replayed_incident.category == IncidentCategory.DATA_LEAK
    assert replayed_incident.source == IncidentSource.AUTOMATED_MONITOR
    assert replayed_incident.confirmed is False


# --- Тесты миграции схемы (v0.7.3) --------------------------------------

def test_migrates_old_schema_file_missing_new_columns():
    """Регрессионный тест на реальный баг: файл базы, созданный до
    появления execution_status/duration_seconds (например, до v0.7.2,
    восстановленный из кэша GitHub Actions), должен получить эти
    колонки автоматически при следующем открытии, а не падать с
    sqlite3.OperationalError при первой же записи."""
    import sqlite3
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "old_schema.db")
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                declared_score REAL NOT NULL,
                declared_label TEXT NOT NULL,
                declared_confidence TEXT,
                genome_hash TEXT,
                genome_version TEXT,
                trust_model_version TEXT,
                evaluation_period TEXT,
                request_count INTEGER,
                schema_version TEXT,
                collector TEXT,
                source TEXT
            );
            CREATE TABLE incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id INTEGER NOT NULL,
                severity TEXT NOT NULL,
                description TEXT,
                category TEXT,
                source TEXT,
                confirmed INTEGER,
                resolution TEXT
            );
            """
        )
        conn.commit()
        conn.close()

        # Открываем старый файл текущим кодом. Раньше здесь падало с
        # "table observations has no column named execution_status".
        store = EvidenceStore(db_path)
        store.record_observation(
            "agent-a", 60.0, "Conditional",
            execution_status="success", duration_seconds=2.5,
        )
        obs = store.get_observations("agent-a")[0]
        assert obs.execution_status == "success"
        assert obs.duration_seconds == 2.5
        store.close()


# --- Тесты производительности (v0.7.6) --------------------------------

def test_get_observations_uses_single_query_not_n_plus_one():
    """Регрессионный тест на реальную находку: get_observations() делал
    N+1 запрос (один за наблюдениями, затем отдельный за инцидентами на
    каждое наблюдение в цикле). На 20000 наблюдениях это давало 315мс и
    20001 отдельный запрос к SQLite. Теперь один JOIN-запрос, независимо
    от количества наблюдений. Проверяем через execute tracing, а не
    только по времени (время нестабильно между окружениями)."""
    store = EvidenceStore(":memory:")
    for i in range(50):
        incidents = [Incident(f"incident {i}", IncidentSeverity.MINOR)] if i % 2 == 0 else []
        store.record_observation("agent-1", declared_score=70.0, declared_label="Conditional", incidents=incidents)

    executed_queries = []
    store._conn.set_trace_callback(lambda sql: executed_queries.append(sql))
    observations = store.get_observations("agent-1")
    store._conn.set_trace_callback(None)

    assert len(observations) == 50
    assert len(executed_queries) == 1, f"Ожидался 1 запрос (JOIN), выполнено {len(executed_queries)}"
    store.close()


def test_get_observations_correctly_groups_multiple_incidents_via_join():
    """После перехода на JOIN критично проверить, что наблюдение с
    несколькими инцидентами не размножается на несколько наблюдений
    (частая ошибка при ручной группировке результатов JOIN)."""
    store = EvidenceStore(":memory:")
    store.record_observation("agent-1", declared_score=50.0, declared_label="High Risk", incidents=[
        Incident("a", IncidentSeverity.MINOR),
        Incident("b", IncidentSeverity.MODERATE),
        Incident("c", IncidentSeverity.SEVERE),
    ])
    observations = store.get_observations("agent-1")
    assert len(observations) == 1  # не 3
    assert len(observations[0].incidents) == 3
    store.close()


def test_get_observations_preserves_order_with_join():
    store = EvidenceStore(":memory:")
    for score in [10.0, 20.0, 30.0]:
        store.record_observation("agent-1", declared_score=score, declared_label="High Risk")
    observations = store.get_observations("agent-1")
    assert [o.declared_score for o in observations] == [10.0, 20.0, 30.0]
    store.close()


def test_file_based_store_uses_wal_journal_mode():
    """WAL позволяет одному писателю и нескольким читателям работать
    одновременно без 'database is locked'. Найдено внешним разбором
    как реальный, ранее не учтённый пробел."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "wal_test.db")
        store = EvidenceStore(db_path)
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        store.close()


def test_memory_store_does_not_break_with_wal_guard():
    """:memory: не поддерживает WAL вообще, проверяем, что попытка его
    включить не была применена и не сломала запись/чтение."""
    store = EvidenceStore(":memory:")
    store.record_observation("agent-1", 80.0, "Trusted")
    assert store.count_observations("agent-1") == 1
    store.close()


# --- model_version/prompt_version (v0.7.11) -----------------------------

def test_model_and_prompt_version_persisted():
    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-1", 70.0, "Conditional",
        model_version="groq/openai/gpt-oss-20b", prompt_version="v3",
    )
    obs = store.get_observations("agent-1")[0]
    assert obs.model_version == "groq/openai/gpt-oss-20b"
    assert obs.prompt_version == "v3"
    store.close()


def test_model_and_prompt_version_default_to_none():
    """agenomics не знает, какую модель вызывал агент, поэтому ничего
    не подставляет, в отличие от trust_model_version."""
    store = EvidenceStore(":memory:")
    store.record_observation("agent-1", 70.0, "Conditional")
    obs = store.get_observations("agent-1")[0]
    assert obs.model_version is None
    assert obs.prompt_version is None
    store.close()


def test_model_and_prompt_version_in_exports():
    store = EvidenceStore(":memory:")
    store.record_observation("agent-1", 70.0, "Conditional", model_version="m1", prompt_version="p1")
    with tempfile.TemporaryDirectory() as tmp:
        json_path = store.export_json(os.path.join(tmp, "out.json"))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data[0]["model_version"] == "m1"
        assert data[0]["prompt_version"] == "p1"

        csv_path = store.export_csv(os.path.join(tmp, "out.csv"))
        with open(csv_path, encoding="utf-8") as f:
            header, row = f.read().splitlines()[:2]
        columns = header.split(",")
        values = row.split(",")
        assert values[columns.index("model_version")] == "m1"
        assert values[columns.index("prompt_version")] == "p1"
    store.close()


def test_migrates_v0710_schema_file_missing_model_and_prompt_version():
    """Файл базы, созданный на 0.7.10 (уже с execution_status, но без
    model_version/prompt_version), например восстановленный из кэша
    GitHub Actions, получает новые колонки при открытии. Старые записи
    остаются, новые поля у них None."""
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "v0710.db")
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                declared_score REAL NOT NULL,
                declared_label TEXT NOT NULL,
                declared_confidence TEXT,
                genome_hash TEXT,
                genome_version TEXT,
                trust_model_version TEXT,
                evaluation_period TEXT,
                request_count INTEGER,
                schema_version TEXT,
                collector TEXT,
                source TEXT,
                execution_status TEXT,
                duration_seconds REAL
            );
            CREATE TABLE incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id INTEGER NOT NULL,
                severity TEXT NOT NULL,
                description TEXT,
                category TEXT,
                source TEXT,
                confirmed INTEGER,
                resolution TEXT
            );
            INSERT INTO observations (agent_id, timestamp, declared_score, declared_label, execution_status)
            VALUES ('agent-a', '2026-09-01T00:00:00+00:00', 55.0, 'Conditional', 'success');
            """
        )
        conn.commit()
        conn.close()

        store = EvidenceStore(db_path)
        store.record_observation("agent-a", 60.0, "Conditional", model_version="m2", prompt_version="p2")
        old, new = store.get_observations("agent-a")
        assert old.execution_status == "success"
        assert old.model_version is None and old.prompt_version is None
        assert new.model_version == "m2" and new.prompt_version == "p2"
        store.close()


def test_infrastructure_category_roundtrips_through_replay():
    """IncidentCategory.INFRASTRUCTURE (v0.7.12) сохраняется и
    восстанавливается replay_into_evaluation_layer() без ошибки enum."""
    from agenomics import IncidentCategory
    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-1", 60.0, "Conditional",
        incidents=[Incident("ImportError", IncidentSeverity.SEVERE, category=IncidentCategory.INFRASTRUCTURE)],
    )
    assert store.get_observations("agent-1")[0].incidents[0]["category"] == "infrastructure"
    layer = RealWorldEvaluationLayer()
    assert replay_into_evaluation_layer(store, layer, "agent-1") == 1
    store.close()


# --- v0.8.0: framework_version, observed_model_version, независимость ----

def test_framework_and_observed_model_version_persisted_and_exported():
    store = EvidenceStore(":memory:")
    store.record_observation(
        "agent-1", 70.0, "Conditional", model_version="groq/openai/gpt-oss-20b",
        framework_version="crewai==0.1.0", observed_model_version="openai/gpt-oss-20b",
    )
    obs = store.get_observations("agent-1")[0]
    assert obs.framework_version == "crewai==0.1.0"
    assert obs.observed_model_version == "openai/gpt-oss-20b"
    with tempfile.TemporaryDirectory() as tmp:
        with open(store.export_json(os.path.join(tmp, "o.json")), encoding="utf-8") as f:
            assert json.load(f)[0]["framework_version"] == "crewai==0.1.0"
        with open(store.export_csv(os.path.join(tmp, "o.csv")), encoding="utf-8") as f:
            assert "observed_model_version" in f.readline()
    store.close()


def test_migrates_v0712_schema_file_missing_v080_columns():
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "v0712.db")
        old = EvidenceStore(db_path)
        old.close()
        conn = sqlite3.connect(db_path)
        # Имитируем файл 0.7.12: пересоздаём таблицу без колонок v0.8.0.
        conn.executescript(
            """
            DROP TABLE observations;
            CREATE TABLE observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, timestamp TEXT NOT NULL,
                declared_score REAL NOT NULL, declared_label TEXT NOT NULL, declared_confidence TEXT,
                genome_hash TEXT, genome_version TEXT, trust_model_version TEXT, evaluation_period TEXT,
                request_count INTEGER, schema_version TEXT, collector TEXT, source TEXT,
                execution_status TEXT, duration_seconds REAL, model_version TEXT, prompt_version TEXT
            );
            """
        )
        conn.commit()
        conn.close()
        store = EvidenceStore(db_path)
        store.record_observation("a", 50.0, "Conditional", framework_version="x==1")
        assert store.get_observations("a")[0].framework_version == "x==1"
        store.close()


def test_report_counts_unique_genomes_after_replay():
    store = EvidenceStore(":memory:")
    for i in range(12):
        store.record_observation(
            "agent-1", 60.0 + i, "Conditional", genome_hash="g1" if i < 10 else "g2",
            incidents=[Incident("x", IncidentSeverity.MINOR)] if i % 3 == 0 else [],
        )
    layer = RealWorldEvaluationLayer()
    replay_into_evaluation_layer(store, layer, "agent-1")
    report = layer.trust_reality_report("agent-1")
    assert report.n_observations == 12
    assert report.n_unique_genomes == 2
    assert "Уникальных геномов среди 12 наблюдений: 2" in report.detail
    store.close()


def test_report_unique_genomes_unknown_without_hashes():
    layer = RealWorldEvaluationLayer(min_observations=1)
    layer.record_raw_observation("a", 50.0, "Conditional")
    layer.record_raw_observation("a", 60.0, "Conditional", incidents=[Incident("x", IncidentSeverity.MINOR)])
    report = layer.trust_reality_report("a")
    assert report.n_unique_genomes is None
