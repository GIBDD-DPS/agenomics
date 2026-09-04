"""
evidence.py — Evidence Store (v0.7.0).

Автор: Dm.Andreyanov
Проект: Prizolov Lab

Закрывает ограничение, зафиксированное во всём проекте с v0.6.0:
RealWorldEvaluationLayer держит наблюдения только in-memory — состояние
пропадает вместе с процессом. Для настоящей longitudinal-выборки (то,
что нужно, чтобы Incident Correlation перестала быть not_computable
на реальных данных) наблюдения должны переживать перезапуск.

EvidenceStore использует sqlite3 — часть стандартной библиотеки Python,
без новых внешних зависимостей (тот же принцип, что и у остального ядра
agenomics). По умолчанию — файл на диске; ":memory:" — для тестов.

НЕ заменяет RealWorldEvaluationLayer — дополняет его персистентностью.
EvidenceStore хранит сырые записи и умеет их выгружать
(JSON/CSV) и подгружать обратно в RealWorldEvaluationLayer для анализа.
"""

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .feedback import Incident, IncidentSeverity

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    declared_score REAL NOT NULL,
    declared_label TEXT NOT NULL,
    declared_confidence TEXT,
    genome_hash TEXT,
    agenomics_version TEXT
);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    severity TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY(observation_id) REFERENCES observations(id)
);

CREATE INDEX IF NOT EXISTS idx_observations_agent_id ON observations(agent_id);
CREATE INDEX IF NOT EXISTS idx_incidents_observation_id ON incidents(observation_id);
"""


@dataclass
class StoredObservation:
    id: int
    agent_id: str
    timestamp: str
    declared_score: float
    declared_label: str
    declared_confidence: Optional[str]
    genome_hash: Optional[str]
    agenomics_version: Optional[str]
    incidents: List[Dict] = field(default_factory=list)


class EvidenceStore:
    """
    Персистентное (SQLite) хранилище наблюдений и инцидентов — provenance-
    слой поверх RealWorldEvaluationLayer. Не заменяет его логику подсчёта
    корреляции — только переживает перезапуск процесса.
    """

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
        agenomics_version: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Сохраняет одно наблюдение + связанные инциденты. Возвращает id записи."""
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()

        if agenomics_version is None:
            from . import __version__ as _current_version
            agenomics_version = _current_version

        cur = self._conn.execute(
            "INSERT INTO observations "
            "(agent_id, timestamp, declared_score, declared_label, declared_confidence, genome_hash, agenomics_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_id, ts, declared_score, declared_label, declared_confidence, genome_hash, agenomics_version),
        )
        obs_id = cur.lastrowid

        for incident in (incidents or []):
            severity_value = (
                incident.severity.value if hasattr(incident.severity, "value") else incident.severity
            )
            self._conn.execute(
                "INSERT INTO incidents (observation_id, severity, description) VALUES (?, ?, ?)",
                (obs_id, severity_value, incident.description),
            )

        self._conn.commit()
        return obs_id

    def get_observations(self, agent_id: Optional[str] = None) -> List[StoredObservation]:
        """Возвращает наблюдения (все, либо только для agent_id), с вложенными инцидентами."""
        cols = "id, agent_id, timestamp, declared_score, declared_label, declared_confidence, genome_hash, agenomics_version"
        if agent_id is not None:
            rows = self._conn.execute(
                f"SELECT {cols} FROM observations WHERE agent_id = ? ORDER BY id", (agent_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(f"SELECT {cols} FROM observations ORDER BY id").fetchall()

        observations = []
        for row in rows:
            obs_id = row[0]
            incident_rows = self._conn.execute(
                "SELECT severity, description FROM incidents WHERE observation_id = ?", (obs_id,)
            ).fetchall()
            observations.append(StoredObservation(
                id=row[0], agent_id=row[1], timestamp=row[2], declared_score=row[3],
                declared_label=row[4], declared_confidence=row[5], genome_hash=row[6],
                agenomics_version=row[7],
                incidents=[{"severity": r[0], "description": r[1]} for r in incident_rows],
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
                "genome_hash": o.genome_hash, "agenomics_version": o.agenomics_version,
                "incidents": o.incidents,
            }
            for o in observations
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def export_csv(self, path: str, agent_id: Optional[str] = None) -> str:
        """Плоский CSV — одна строка на наблюдение, инциденты агрегированы
        в счётчик по тяжести (детали инцидентов доступны только в export_json)."""
        observations = self.get_observations(agent_id)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id", "agent_id", "timestamp", "declared_score", "declared_label",
                "declared_confidence", "genome_hash", "agenomics_version", "n_incidents",
                "n_minor", "n_moderate", "n_severe",
            ])
            for o in observations:
                counts = {"minor": 0, "moderate": 0, "severe": 0}
                for inc in o.incidents:
                    if inc["severity"] in counts:
                        counts[inc["severity"]] += 1
                writer.writerow([
                    o.id, o.agent_id, o.timestamp, o.declared_score, o.declared_label,
                    o.declared_confidence, o.genome_hash, o.agenomics_version, len(o.incidents),
                    counts["minor"], counts["moderate"], counts["severe"],
                ])
        return path

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def replay_into_evaluation_layer(store: EvidenceStore, layer, agent_id: Optional[str] = None) -> int:
    """
    Загружает сохранённые наблюдения из EvidenceStore обратно в
    RealWorldEvaluationLayer (agenomics.evaluation) — например, после
    перезапуска процесса, когда сам layer уже пуст (in-memory).

    Принимает layer как duck-typed объект с методом record_raw_observation(),
    а не импортирует RealWorldEvaluationLayer напрямую — чтобы не создавать
    циклическую зависимость evidence.py <-> evaluation.py (evaluation.py
    не должен знать про персистентность, а evidence.py не должен быть
    единственным способом наполнить layer).

    Возвращает количество воспроизведённых наблюдений.
    """
    from .feedback import Incident, IncidentSeverity

    observations = store.get_observations(agent_id)
    for obs in observations:
        incidents = [
            Incident(description=inc.get("description") or "", severity=IncidentSeverity(inc["severity"]))
            for inc in obs.incidents
        ]
        layer.record_raw_observation(
            agent_id=obs.agent_id,
            score=obs.declared_score,
            label=obs.declared_label,
            confidence=obs.declared_confidence or "High",
            incidents=incidents,
            timestamp=datetime.fromisoformat(obs.timestamp),
        )
    return len(observations)
