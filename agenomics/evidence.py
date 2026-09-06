"""
evidence.py. Персистентное хранилище наблюдений и инцидентов по схеме AEP-001.

Автор: Dm.Andreyanov
Проект: Prizolov Lab

До этого модуля RealWorldEvaluationLayer хранил наблюдения только в памяти
процесса, и всё пропадало при перезапуске. EvidenceStore решает именно это:
пишет в обычный SQLite-файл, который переживает рестарт.

Схема соответствует Agenomics Evidence Protocol v1.0 (docs/AEP-001.md).

Использует sqlite3 из стандартной библиотеки, новых зависимостей нет.
По умолчанию пишет в файл на диске, для тестов можно передать ":memory:".

Не заменяет RealWorldEvaluationLayer, а дополняет его персистентностью.
"""

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .feedback import Incident, IncidentCategory, IncidentSeverity, IncidentSource

AEP_SCHEMA_VERSION = "1.0"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS observations (
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

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    severity TEXT NOT NULL,
    description TEXT,
    category TEXT,
    source TEXT,
    confirmed INTEGER,
    resolution TEXT,
    FOREIGN KEY(observation_id) REFERENCES observations(id)
);

CREATE INDEX IF NOT EXISTS idx_observations_agent_id ON observations(agent_id);
CREATE INDEX IF NOT EXISTS idx_incidents_observation_id ON incidents(observation_id);
"""

_OBSERVATION_COLS = (
    "id, agent_id, timestamp, declared_score, declared_label, declared_confidence, "
    "genome_hash, genome_version, trust_model_version, evaluation_period, "
    "request_count, schema_version, collector, source, execution_status, duration_seconds"
)


@dataclass
class StoredObservation:
    id: int
    agent_id: str
    timestamp: str
    declared_score: float
    declared_label: str
    declared_confidence: Optional[str]
    genome_hash: Optional[str]
    genome_version: Optional[str] = None
    trust_model_version: Optional[str] = None
    evaluation_period: Optional[str] = None
    request_count: Optional[int] = None
    schema_version: Optional[str] = None
    collector: Optional[str] = None
    source: Optional[str] = None
    execution_status: Optional[str] = None
    duration_seconds: Optional[float] = None
    incidents: List[Dict] = field(default_factory=list)


class EvidenceStore:
    """Хранит наблюдения и инциденты в SQLite по схеме AEP-001.
    Не заменяет RealWorldEvaluationLayer, только даёт ему пережить рестарт."""

    def __init__(self, db_path: str = "agenomics_evidence.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def record_observation(
        self,
        agent_id: str,
        declared_score: float,
        declared_label: str,
        declared_confidence: Optional[str] = None,
        incidents: Optional[List[Incident]] = None,
        genome_hash: Optional[str] = None,
        agenomics_version: Optional[str] = None,  # алиас trust_model_version, для обратной совместимости с v0.7.0
        genome_version: Optional[str] = None,
        trust_model_version: Optional[str] = None,
        evaluation_period: Optional[str] = None,
        request_count: Optional[int] = None,
        collector: Optional[str] = None,
        source: Optional[str] = None,
        execution_status: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Сохраняет одно наблюдение и связанные инциденты по схеме AEP-001.
        Возвращает id записи.

        agenomics_version это старое имя параметра из v0.7.0, оставлено
        как алиас trust_model_version для обратной совместимости. Если
        передано и то, и другое, побеждает trust_model_version.

        execution_status ("success" или "error") и duration_seconds
        нужны, чтобы честно восстанавливать историю запусков после
        перезапуска процесса, например между запусками GitHub Actions.
        Раньше статус приходилось угадывать по тексту описания инцидента."""
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()

        resolved_trust_model_version = trust_model_version or agenomics_version
        if resolved_trust_model_version is None:
            from . import __version__ as _current_version
            resolved_trust_model_version = _current_version

        cur = self._conn.execute(
            "INSERT INTO observations "
            "(agent_id, timestamp, declared_score, declared_label, declared_confidence, "
            "genome_hash, genome_version, trust_model_version, evaluation_period, "
            "request_count, schema_version, collector, source, execution_status, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                agent_id, ts, declared_score, declared_label, declared_confidence,
                genome_hash, genome_version, resolved_trust_model_version, evaluation_period,
                request_count, AEP_SCHEMA_VERSION, collector, source, execution_status, duration_seconds,
            ),
        )
        obs_id = cur.lastrowid

        for incident in (incidents or []):
            severity_value = incident.severity.value if hasattr(incident.severity, "value") else incident.severity
            category_value = (
                incident.category.value if getattr(incident, "category", None) is not None
                and hasattr(incident.category, "value") else getattr(incident, "category", None)
            )
            source_value = (
                incident.source.value if getattr(incident, "source", None) is not None
                and hasattr(incident.source, "value") else getattr(incident, "source", None)
            )
            confirmed_value = int(getattr(incident, "confirmed", True))
            resolution_value = getattr(incident, "resolution", None)

            self._conn.execute(
                "INSERT INTO incidents "
                "(observation_id, severity, description, category, source, confirmed, resolution) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (obs_id, severity_value, incident.description, category_value, source_value,
                 confirmed_value, resolution_value),
            )

        self._conn.commit()
        return obs_id

    def get_observations(self, agent_id: Optional[str] = None) -> List[StoredObservation]:
        """Возвращает наблюдения, все или только по agent_id, вместе с их инцидентами."""
        if agent_id is not None:
            rows = self._conn.execute(
                f"SELECT {_OBSERVATION_COLS} FROM observations WHERE agent_id = ? ORDER BY id", (agent_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(f"SELECT {_OBSERVATION_COLS} FROM observations ORDER BY id").fetchall()

        observations = []
        for row in rows:
            obs_id = row[0]
            incident_rows = self._conn.execute(
                "SELECT severity, description, category, source, confirmed, resolution "
                "FROM incidents WHERE observation_id = ?", (obs_id,),
            ).fetchall()
            observations.append(StoredObservation(
                id=row[0], agent_id=row[1], timestamp=row[2], declared_score=row[3],
                declared_label=row[4], declared_confidence=row[5], genome_hash=row[6],
                genome_version=row[7], trust_model_version=row[8], evaluation_period=row[9],
                request_count=row[10], schema_version=row[11], collector=row[12], source=row[13],
                execution_status=row[14], duration_seconds=row[15],
                incidents=[
                    {
                        "severity": r[0], "description": r[1], "category": r[2],
                        "source": r[3], "confirmed": bool(r[4]) if r[4] is not None else None,
                        "resolution": r[5],
                    }
                    for r in incident_rows
                ],
            ))
        return observations

    def count_observations(self, agent_id: Optional[str] = None) -> int:
        if agent_id is not None:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM observations WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM observations").fetchone()
        return row[0]

    def export_json(self, path: str, agent_id: Optional[str] = None) -> str:
        observations = self.get_observations(agent_id)
        data = [
            {
                "id": o.id, "agent_id": o.agent_id, "timestamp": o.timestamp,
                "declared_score": o.declared_score, "declared_label": o.declared_label,
                "declared_confidence": o.declared_confidence,
                "genome_hash": o.genome_hash, "genome_version": o.genome_version,
                "trust_model_version": o.trust_model_version,
                "evaluation_period": o.evaluation_period, "request_count": o.request_count,
                "schema_version": o.schema_version, "collector": o.collector, "source": o.source,
                "execution_status": o.execution_status, "duration_seconds": o.duration_seconds,
                "incidents": o.incidents,
            }
            for o in observations
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def export_csv(self, path: str, agent_id: Optional[str] = None) -> str:
        """Плоский CSV, одна строка на наблюдение. Инциденты сведены к счётчику
        по тяжести, детали доступны только через export_json."""
        observations = self.get_observations(agent_id)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id", "agent_id", "timestamp", "declared_score", "declared_label",
                "declared_confidence", "genome_hash", "genome_version", "trust_model_version",
                "evaluation_period", "request_count", "schema_version", "collector", "source",
                "execution_status", "duration_seconds",
                "n_incidents", "n_minor", "n_moderate", "n_severe",
            ])
            for o in observations:
                counts = {"minor": 0, "moderate": 0, "severe": 0}
                for inc in o.incidents:
                    if inc["severity"] in counts:
                        counts[inc["severity"]] += 1
                writer.writerow([
                    o.id, o.agent_id, o.timestamp, o.declared_score, o.declared_label,
                    o.declared_confidence, o.genome_hash, o.genome_version, o.trust_model_version,
                    o.evaluation_period, o.request_count, o.schema_version, o.collector, o.source,
                    o.execution_status, o.duration_seconds,
                    len(o.incidents), counts["minor"], counts["moderate"], counts["severe"],
                ])
        return path

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def replay_into_evaluation_layer(store: EvidenceStore, layer, agent_id: Optional[str] = None) -> int:
    """Загружает сохранённые наблюдения из EvidenceStore обратно в
    RealWorldEvaluationLayer. Пригодится после перезапуска процесса,
    когда сам layer уже пуст.

    Возвращает количество загруженных наблюдений."""
    observations = store.get_observations(agent_id)
    for obs in observations:
        incidents = []
        for inc in obs.incidents:
            incidents.append(Incident(
                description=inc.get("description") or "",
                severity=IncidentSeverity(inc["severity"]),
                category=IncidentCategory(inc["category"]) if inc.get("category") else None,
                source=IncidentSource(inc["source"]) if inc.get("source") else None,
                confirmed=inc.get("confirmed") if inc.get("confirmed") is not None else True,
                resolution=inc.get("resolution"),
            ))
        layer.record_raw_observation(
            agent_id=obs.agent_id,
            score=obs.declared_score,
            label=obs.declared_label,
            confidence=obs.declared_confidence or "High",
            incidents=incidents,
            timestamp=datetime.fromisoformat(obs.timestamp),
        )
    return len(observations)
