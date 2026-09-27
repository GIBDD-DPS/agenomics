# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
evidence_graph.py. Доноры, доказательства, предсказания и исходы (AEP-001 v1.1).

Автор: Dm.Andreyanov
Проект: Prizolov Lab

До v0.9.0 EvidenceStore хранил наблюдения и инциденты, но не то, КТО
сообщил каждое доказательство. Из-за этого 100 оценок от одного и того
же LLM-судьи выглядели как 100 независимых подтверждений, хотя это один
сигнал, повторённый 100 раз.

Четыре сущности:

- Donor: источник доказательств (runtime-монитор, сканер секретов,
  LLM-судья, человек, реальный исход). independence_group определяет
  независимость: два судьи на одной модели одного провайдера это два
  донора, но одна группа.
- Evidence: одно доказательство от одного донора об одном наблюдении,
  с уровнем качества Q0-Q4.
- Prediction: Trust Score, замороженный ДО выполнения задачи, и то, что
  он предсказывает (target) на каком горизонте (horizon).
- Outcome: что реально произошло, от конкретного донора, строго после
  заморозки предсказания. Исходов от разных доноров может быть несколько,
  противоречащие друг другу сохраняются оба.

Доноры поставляют доказательства, а не определяют истину, и в Trust Score
не входят. Сопоставление предсказаний с исходами это работа следующего
слоя (Validation Engine, roadmap v0.9.x), здесь только честное хранение.

Реализовано как миксин EvidenceStore: те же SQLite-файл и соединение.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

DONOR_TYPES = ("execution", "outcome", "judge", "security", "human")

# Уровни качества доказательства. Шкала упорядочена: Q4 сильнее Q0.
QUALITY_LEVELS = {
    "Q0": "синтетика или тест",
    "Q1": "инфраструктурный сигнал (упал / не упал)",
    "Q2": "автоматическая проверка поведения (сканер, пробы)",
    "Q3": "LLM-судья или подтверждённый автоматический исход",
    "Q4": "человек или реальный исход в продакшене",
}

VERIFICATION_METHODS = ("automated", "human", "ground_truth")

# [v0.9.6] Класс исхода: что именно случилось, независимо от конкретного
# outcome_type. Подтип сбоя окружения (провайдер, зависимости) не отдельный
# класс: он уже есть в классе ошибки и пишется в details.
OUTCOME_CLASSES = ("TASK", "SECURITY", "RUNTIME", "BEHAVIORAL", "INFRASTRUCTURE")
OUTCOME_CLASS_BY_TYPE = {
    "task_failure": "TASK",
    "secret_leak": "SECURITY",
    "execution_error": "RUNTIME",
    "infrastructure_error": "INFRASTRUCTURE",
}

# Поля снимка предсказания: копируются из наблюдения в момент заморозки.
SNAPSHOT_OBSERVATION_FIELDS = (
    "trust_model_version", "genome_hash", "genome_version", "model_version",
    "prompt_version", "framework_version",
)

GRAPH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS donors (
    donor_id TEXT PRIMARY KEY,
    donor_type TEXT NOT NULL,
    name TEXT NOT NULL,
    independence_group TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    version TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    donor_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    finding TEXT NOT NULL,
    quality_level TEXT NOT NULL,
    confidence REAL,
    source_reference TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(observation_id) REFERENCES observations(id),
    FOREIGN KEY(donor_id) REFERENCES donors(donor_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    trust_score REAL NOT NULL,
    target TEXT NOT NULL,
    horizon TEXT NOT NULL,
    frozen_at TEXT NOT NULL,
    FOREIGN KEY(observation_id) REFERENCES observations(id)
);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER NOT NULL,
    donor_id TEXT NOT NULL,
    outcome_type TEXT NOT NULL,
    occurred INTEGER NOT NULL,
    verification TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    details TEXT,
    FOREIGN KEY(prediction_id) REFERENCES predictions(id),
    FOREIGN KEY(donor_id) REFERENCES donors(donor_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_observation_id ON evidence(observation_id);
CREATE INDEX IF NOT EXISTS idx_predictions_agent_id ON predictions(agent_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_prediction_id ON outcomes(prediction_id);
"""

# [v0.9.6] Колонки, добавленные после появления таблиц. Файл базы старой
# версии получает их миграцией (_migrate_graph_schema), как observations
# в evidence.py.
_EXPECTED_GRAPH_COLUMNS = {
    "predictions": {
        **{f: "TEXT" for f in SNAPSHOT_OBSERVATION_FIELDS},
        "task_version": "TEXT", "environment_id": "TEXT",
        "snapshot_json": "TEXT", "snapshot_sha256": "TEXT",
    },
    "outcomes": {
        "outcome_class": "TEXT", "quality_level": "TEXT", "source_reference": "TEXT",
        "collector_version": "TEXT", "fingerprint": "TEXT",
    },
    "evidence": {"collector_version": "TEXT", "fingerprint": "TEXT"},
}

_APPEND_ONLY_TABLES = ("predictions", "outcomes", "evidence")

# Триггеры создаются после миграции: заполнение новых колонок старых строк
# идёт до них. Исправление записи оформляется новой строкой.
GRAPH_CONSTRAINTS_SQL = "".join(
    f"""
CREATE TRIGGER IF NOT EXISTS {t}_no_update BEFORE UPDATE ON {t}
BEGIN SELECT RAISE(ABORT, '{t} are append-only'); END;
CREATE TRIGGER IF NOT EXISTS {t}_no_delete BEFORE DELETE ON {t}
BEGIN SELECT RAISE(ABORT, '{t} are append-only'); END;
""" for t in _APPEND_ONLY_TABLES
) + """
CREATE UNIQUE INDEX IF NOT EXISTS ux_evidence_fingerprint ON evidence(fingerprint) WHERE fingerprint IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_outcomes_fingerprint ON outcomes(fingerprint) WHERE fingerprint IS NOT NULL;
"""

_BACKFILL_MARKER = "graph_backfill_0.9.6"


def _fingerprint(*parts) -> str:
    return hashlib.sha256("|".join("" if p is None else str(p) for p in parts).encode("utf-8")).hexdigest()


def _collector_version() -> str:
    from . import __version__
    return __version__


@dataclass
class Donor:
    donor_id: str
    donor_type: str
    name: str
    independence_group: str
    provider: Optional[str] = None
    model: Optional[str] = None
    version: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class StoredEvidence:
    id: int
    observation_id: int
    donor_id: str
    independence_group: str  # из донора, не хранится отдельно: не может разойтись с ним
    evidence_type: str
    finding: str
    quality_level: str
    confidence: Optional[float]
    source_reference: Optional[str]
    created_at: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class StoredOutcome:
    id: int
    donor_id: str
    independence_group: str
    outcome_type: str
    occurred: bool
    verification: str
    observed_at: str
    details: Optional[str] = None
    outcome_class: Optional[str] = None     # [v0.9.6]
    quality_level: Optional[str] = None     # [v0.9.6]
    source_reference: Optional[str] = None  # [v0.9.6]


@dataclass
class StoredPrediction:
    id: int
    observation_id: int
    agent_id: str
    trust_score: float
    target: str
    horizon: str
    frozen_at: str
    outcomes: List[StoredOutcome] = field(default_factory=list)
    # [v0.9.6] Снимок на момент заморозки; пуст у предсказаний до v0.9.6.
    snapshot: Dict = field(default_factory=dict)


@dataclass
class EvidenceProfile:
    """Сколько и каких доказательств есть, отдельно по объёму, качеству и
    независимости. Ни одно из этих чисел не заменяет другое: 100
    доказательств из одной независимой группы слабее 10 из пяти групп."""
    agent_id: Optional[str]
    n_observations: int
    n_agents: int
    n_genomes: int
    n_evidence: int
    n_donors: int
    n_independence_groups: int
    independence_groups: Dict[str, int]  # группа -> число доказательств
    evidence_by_quality: Dict[str, int]
    n_predictions: int
    n_predictions_with_outcome: int
    n_verified_outcomes: int  # verification = human или ground_truth
    # [v0.9.6] Среди наблюдений, у которых есть предсказания: одно наблюдение
    # (прогон) даёт по предсказанию на каждую цель, поэтому число
    # предсказаний не равно числу независимых прогонов.
    n_predicted_observations: int = 0
    n_predicted_agents: int = 0
    n_predicted_genomes: int = 0
    # [v0.9.6] Повторы, не вошедшие в счёт: доказательства и исходы без
    # отпечатка после миграции (совпали с уже записанными) и лишние
    # предсказания той же цели для того же наблюдения.
    n_duplicate_evidence: int = 0
    n_duplicate_outcomes: int = 0
    n_duplicate_predictions: int = 0
    n_outcomes_without_class: int = 0
    # Качество самих исходов. Q4 бывает только у исходов (внешнее
    # подтверждение, record_external_outcome), у доказательств его может не
    # быть вовсе, поэтому считать Q4 только по доказательствам нельзя.
    outcomes_by_quality: Dict[str, int] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(ts: datetime) -> datetime:
    """Время без часового пояса считается UTC: иначе сравнение с
    сохранённым временем в UTC падает с TypeError."""
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def _iso(ts: Optional[datetime]) -> str:
    return _aware(ts or _now()).isoformat()


def _parse(ts: str) -> datetime:
    return _aware(datetime.fromisoformat(ts))


class EvidenceGraphMixin:
    """Методы Evidence Graph для EvidenceStore. Ожидает self._conn."""

    # --- Schema ------------------------------------------------------------

    def _migrate_graph_schema(self) -> None:
        """[v0.9.6] Новые колонки графовых таблиц, однократное заполнение
        их у старых строк, затем триггеры неизменяемости и уникальные
        индексы. Заполнение детерминированно и без догадок: класс исхода
        только по таблице соответствия, отпечаток по полям строки; то, что
        так не определяется, остаётся NULL. Старые строки не удаляются."""
        conn = self._conn
        for table, columns in _EXPECTED_GRAPH_COLUMNS.items():
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for column, sql_type in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        done = conn.execute("SELECT 1 FROM schema_meta WHERE key = ?", (_BACKFILL_MARKER,)).fetchone()
        if not done:
            for table in _APPEND_ONLY_TABLES:
                conn.execute(f"DROP TRIGGER IF EXISTS {table}_no_update")
                conn.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete")
            self._backfill_graph()
            conn.execute("INSERT INTO schema_meta (key, value) VALUES (?, ?)", (_BACKFILL_MARKER, _iso(None)))
        conn.executescript(GRAPH_CONSTRAINTS_SQL)
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM (SELECT 1 FROM predictions GROUP BY observation_id, target, horizon HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        if not duplicates:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_predictions_obs_target ON predictions(observation_id, target, horizon)"
            )
        conn.commit()

    def _backfill_graph(self) -> None:
        conn = self._conn
        for outcome_type, outcome_class in OUTCOME_CLASS_BY_TYPE.items():
            conn.execute(
                "UPDATE outcomes SET outcome_class = ? WHERE outcome_class IS NULL AND outcome_type = ?",
                (outcome_class, outcome_type),
            )
        # Качество исхода: лучший уровень доказательства того же донора по
        # тому же наблюдению (Q0 < ... < Q4 совпадает со строковым порядком).
        conn.execute(
            "UPDATE outcomes SET quality_level = ("
            "  SELECT MAX(e.quality_level) FROM evidence e JOIN predictions p ON p.observation_id = e.observation_id"
            "  WHERE p.id = outcomes.prediction_id AND e.donor_id = outcomes.donor_id"
            ") WHERE quality_level IS NULL"
        )
        seen = {r[0] for r in conn.execute("SELECT fingerprint FROM evidence WHERE fingerprint IS NOT NULL")}
        for row_id, obs_id, donor_id, evidence_type, reference in conn.execute(
            "SELECT id, observation_id, donor_id, evidence_type, source_reference FROM evidence "
            "WHERE fingerprint IS NULL ORDER BY id"
        ).fetchall():
            fp = _fingerprint(obs_id, donor_id, evidence_type, reference)
            if fp not in seen:  # повтор оставляется без отпечатка и считается в профиле
                seen.add(fp)
                conn.execute("UPDATE evidence SET fingerprint = ? WHERE id = ?", (fp, row_id))
        seen = {r[0] for r in conn.execute("SELECT fingerprint FROM outcomes WHERE fingerprint IS NOT NULL")}
        for row_id, pred_id, donor_id, outcome_type, reference in conn.execute(
            "SELECT id, prediction_id, donor_id, outcome_type, source_reference FROM outcomes "
            "WHERE fingerprint IS NULL ORDER BY id"
        ).fetchall():
            fp = _fingerprint(pred_id, donor_id, outcome_type, reference)
            if fp not in seen:
                seen.add(fp)
                conn.execute("UPDATE outcomes SET fingerprint = ? WHERE id = ?", (fp, row_id))

    # --- Donors ------------------------------------------------------------

    def register_donor(
        self,
        donor_id: str,
        donor_type: str,
        name: str,
        independence_group: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        version: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Donor:
        """Регистрирует донора. Повторная регистрация с теми же полями
        ничего не делает (удобно вызывать при каждом запуске). С другими
        полями это ValueError: донор, на которого уже ссылаются
        доказательства, не должен молча стать другим источником. Новая
        версия модели судьи это новый donor_id."""
        if donor_type not in DONOR_TYPES:
            raise ValueError(f"donor_type должен быть одним из {DONOR_TYPES}, получено {donor_type!r}")
        if not independence_group:
            raise ValueError("independence_group обязателен: без него независимость доказательств не оценить")
        donor = Donor(donor_id, donor_type, name, independence_group, provider, model, version, dict(metadata or {}))
        existing = self.get_donor(donor_id)
        if existing is not None:
            if existing != donor:
                raise ValueError(
                    f"донор {donor_id!r} уже зарегистрирован с другими полями; "
                    f"изменённый источник регистрируйте под новым donor_id"
                )
            return existing
        self._conn.execute(
            "INSERT INTO donors (donor_id, donor_type, name, independence_group, provider, model, version, "
            "metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (donor_id, donor_type, name, independence_group, provider, model, version,
             json.dumps(donor.metadata, ensure_ascii=False, sort_keys=True), _iso(None)),
        )
        self._conn.commit()
        return donor

    def get_donor(self, donor_id: str) -> Optional[Donor]:
        row = self._conn.execute(
            "SELECT donor_id, donor_type, name, independence_group, provider, model, version, metadata_json "
            "FROM donors WHERE donor_id = ?", (donor_id,),
        ).fetchone()
        if row is None:
            return None
        return Donor(*row[:7], metadata=json.loads(row[7] or "{}"))

    def list_donors(self) -> List[Donor]:
        ids = [r[0] for r in self._conn.execute("SELECT donor_id FROM donors ORDER BY donor_id")]
        return [self.get_donor(d) for d in ids]

    def _require_donor(self, donor_id: str) -> Donor:
        donor = self.get_donor(donor_id)
        if donor is None:
            raise ValueError(f"донор {donor_id!r} не зарегистрирован, сначала register_donor()")
        return donor

    def _require_observation(self, observation_id: int) -> None:
        row = self._conn.execute("SELECT 1 FROM observations WHERE id = ?", (observation_id,)).fetchone()
        if row is None:
            raise ValueError(f"наблюдение id={observation_id} не найдено")

    # --- Evidence ----------------------------------------------------------

    def record_evidence(
        self,
        observation_id: int,
        donor_id: str,
        evidence_type: str,
        finding: str,
        quality_level: str,
        confidence: Optional[float] = None,
        source_reference: Optional[str] = None,
        metadata: Optional[Dict] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Одно доказательство от одного донора. finding это короткий
        вывод донора ("clean", "leak:bearer_token", "safe"), не сырой
        текст (AEP-001, Privacy)."""
        self._require_observation(observation_id)
        self._require_donor(donor_id)
        if quality_level not in QUALITY_LEVELS:
            raise ValueError(f"quality_level должен быть одним из {tuple(QUALITY_LEVELS)}, получено {quality_level!r}")
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise ValueError(f"confidence должен быть в [0, 1], получено {confidence}")
        # [v0.9.6] Повтор того же доказательства не пишется второй строкой:
        # иначе N растёт без новых данных. Возвращается id существующей.
        fp = _fingerprint(observation_id, donor_id, evidence_type, source_reference)
        existing = self._conn.execute("SELECT id FROM evidence WHERE fingerprint = ?", (fp,)).fetchone()
        if existing:
            return existing[0]
        cur = self._conn.execute(
            "INSERT INTO evidence (observation_id, donor_id, evidence_type, finding, quality_level, confidence, "
            "source_reference, metadata_json, created_at, collector_version, fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (observation_id, donor_id, evidence_type, finding, quality_level, confidence, source_reference,
             json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True), _iso(timestamp),
             _collector_version(), fp),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_evidence(self, observation_id: Optional[int] = None, agent_id: Optional[str] = None) -> List[StoredEvidence]:
        query = (
            "SELECT e.id, e.observation_id, e.donor_id, d.independence_group, e.evidence_type, e.finding, "
            "e.quality_level, e.confidence, e.source_reference, e.created_at, e.metadata_json "
            "FROM evidence e JOIN donors d ON d.donor_id = e.donor_id "
            "JOIN observations o ON o.id = e.observation_id WHERE 1=1"
        )
        params: list = []
        if observation_id is not None:
            query += " AND e.observation_id = ?"
            params.append(observation_id)
        if agent_id is not None:
            query += " AND o.agent_id = ?"
            params.append(agent_id)
        rows = self._conn.execute(query + " ORDER BY e.id", params).fetchall()
        return [StoredEvidence(*r[:10], metadata=json.loads(r[10] or "{}")) for r in rows]

    # --- Predictions and outcomes ------------------------------------------

    def record_prediction(
        self,
        observation_id: int,
        target: str,
        horizon: str = "next_execution",
        frozen_at: Optional[datetime] = None,
        task_version: Optional[str] = None,
        environment_id: Optional[str] = None,
    ) -> int:
        """Замораживает Trust Score наблюдения как предсказание target на
        горизонте horizon. Score копируется из наблюдения в момент вызова
        и больше не меняется: предсказание не пересчитывается задним
        числом. Вызывайте ДО выполнения задачи; record_outcome() не
        примет исход, наблюдённый раньше frozen_at.

        [v0.9.6] Вместе со score замораживается снимок конфигурации
        (версии модели доверия, генома, модели, промпта, фреймворка,
        задача, окружение) с SHA-256. Таблица только на добавление;
        второе предсказание той же цели на том же горизонте для того же
        наблюдения это ValueError."""
        columns = ("agent_id", "declared_score") + SNAPSHOT_OBSERVATION_FIELDS
        row = self._conn.execute(
            f"SELECT {', '.join(columns)} FROM observations WHERE id = ?", (observation_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"наблюдение id={observation_id} не найдено")
        if self._conn.execute(
            "SELECT 1 FROM predictions WHERE observation_id = ? AND target = ? AND horizon = ?",
            (observation_id, target, horizon),
        ).fetchone():
            raise ValueError(
                f"у наблюдения id={observation_id} уже есть предсказание цели {target!r} на горизонте {horizon!r}"
            )
        frozen = _iso(frozen_at)
        observed = dict(zip(SNAPSHOT_OBSERVATION_FIELDS, row[2:]))
        snapshot = {
            "observation_id": observation_id, "agent_id": row[0], "trust_score": row[1], "target": target,
            "horizon": horizon, "frozen_at": frozen, "task_version": task_version,
            "environment_id": environment_id, **observed,
        }
        snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        cur = self._conn.execute(
            "INSERT INTO predictions (observation_id, agent_id, trust_score, target, horizon, frozen_at, "
            f"{', '.join(SNAPSHOT_OBSERVATION_FIELDS)}, task_version, environment_id, snapshot_json, snapshot_sha256) "
            f"VALUES ({', '.join('?' * (8 + len(SNAPSHOT_OBSERVATION_FIELDS) + 2))})",
            (observation_id, row[0], row[1], target, horizon, frozen, *observed.values(), task_version,
             environment_id, snapshot_json, hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()),
        )
        self._conn.commit()
        return cur.lastrowid

    def verify_prediction_integrity(self) -> Dict:
        """[v0.9.6] Пересчитывает SHA-256 снимка каждого предсказания и
        сверяет поля снимка с колонками. Предсказания до v0.9.6 снимка не
        имеют и считаются отдельно, а не как нарушения."""
        checked, violations, without = 0, [], 0
        columns = ("id", "observation_id", "agent_id", "trust_score", "target", "horizon", "frozen_at",
                   "task_version", "environment_id") + SNAPSHOT_OBSERVATION_FIELDS
        for row in self._conn.execute(
            f"SELECT {', '.join(columns)}, snapshot_json, snapshot_sha256 FROM predictions ORDER BY id"
        ):
            record = dict(zip(columns, row))
            snapshot_json, digest = row[-2], row[-1]
            if snapshot_json is None:
                without += 1
                continue
            checked += 1
            if hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest() != digest:
                violations.append({"prediction_id": record["id"], "problem": "snapshot_sha256"})
                continue
            snapshot = json.loads(snapshot_json)
            mismatched = sorted(k for k, v in snapshot.items() if k in record and k != "id" and record[k] != v)
            if mismatched:
                violations.append({"prediction_id": record["id"], "problem": "fields", "fields": mismatched})
        return {"checked": checked, "without_snapshot": without, "violations": violations}

    def record_outcome(
        self,
        prediction_id: int,
        donor_id: str,
        outcome_type: str,
        occurred: bool,
        verification: str = "automated",
        observed_at: Optional[datetime] = None,
        details: Optional[str] = None,
        outcome_class: Optional[str] = None,
        quality_level: Optional[str] = None,
        source_reference: Optional[str] = None,
    ) -> int:
        """Исход от конкретного донора: произошло ли событие outcome_type.

        [v0.9.6] outcome_class по умолчанию берётся из OUTCOME_CLASS_BY_TYPE
        (для неизвестного типа остаётся пустым и считается в профиле);
        quality_level по умолчанию: лучший уровень доказательства того же
        донора по тому же наблюдению. Повтор того же исхода (тот же
        отпечаток) не пишется, возвращается id существующего.
        observed_at, если передан, обязан быть строго позже frozen_at предсказания,
        иначе это не проверка предсказания, а подгонка под известный
        исход. Несколько исходов от разных доноров допустимы и хранятся
        все, даже если противоречат друг другу."""
        row = self._conn.execute("SELECT frozen_at FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
        if row is None:
            raise ValueError(f"предсказание id={prediction_id} не найдено")
        self._require_donor(donor_id)
        if verification not in VERIFICATION_METHODS:
            raise ValueError(f"verification должен быть одним из {VERIFICATION_METHODS}, получено {verification!r}")
        frozen = _parse(row[0])
        observed = _aware(observed_at or _now())
        # Явно переданное время обязано быть строго позже заморозки. Время
        # по умолчанию (сейчас) позже по порядку вызовов, равенство с
        # frozen_at у него возможно только из-за разрешения часов
        # (на Windows около 15 мс), поэтому для него допускается.
        too_early = observed <= frozen if observed_at is not None else observed < frozen
        if too_early:
            raise ValueError(
                f"исход наблюдён ({observed.isoformat()}) не позже заморозки предсказания ({row[0]}): "
                f"такой исход не может проверять предсказание"
            )
        if details is not None:
            details = details[:200]  # AEP-001, Privacy
        if outcome_class is None:
            outcome_class = OUTCOME_CLASS_BY_TYPE.get(outcome_type)
        elif outcome_class not in OUTCOME_CLASSES:
            raise ValueError(f"outcome_class должен быть одним из {OUTCOME_CLASSES}, получено {outcome_class!r}")
        if quality_level is None:
            quality_level = self._conn.execute(
                "SELECT MAX(e.quality_level) FROM evidence e JOIN predictions p ON p.observation_id = e.observation_id "
                "WHERE p.id = ? AND e.donor_id = ?", (prediction_id, donor_id),
            ).fetchone()[0]
        elif quality_level not in QUALITY_LEVELS:
            raise ValueError(f"quality_level должен быть одним из {tuple(QUALITY_LEVELS)}, получено {quality_level!r}")
        fp = _fingerprint(prediction_id, donor_id, outcome_type, source_reference)
        existing = self._conn.execute("SELECT id FROM outcomes WHERE fingerprint = ?", (fp,)).fetchone()
        if existing:
            return existing[0]
        cur = self._conn.execute(
            "INSERT INTO outcomes (prediction_id, donor_id, outcome_type, occurred, verification, observed_at, details, "
            "outcome_class, quality_level, source_reference, collector_version, fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (prediction_id, donor_id, outcome_type, int(bool(occurred)), verification, observed.isoformat(), details,
             outcome_class, quality_level, source_reference, _collector_version(), fp),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_predictions(self, agent_id: Optional[str] = None) -> List[StoredPrediction]:
        query = ("SELECT id, observation_id, agent_id, trust_score, target, horizon, frozen_at, snapshot_json "
                 "FROM predictions")
        params: list = []
        if agent_id is not None:
            query += " WHERE agent_id = ?"
            params.append(agent_id)
        predictions = [
            StoredPrediction(*r[:7], snapshot=json.loads(r[7]) if r[7] else {})
            for r in self._conn.execute(query + " ORDER BY id", params)
        ]
        by_id = {p.id: p for p in predictions}
        if by_id:
            placeholders = ",".join("?" * len(by_id))
            rows = self._conn.execute(
                "SELECT o.prediction_id, o.id, o.donor_id, d.independence_group, o.outcome_type, o.occurred, "
                "o.verification, o.observed_at, o.details, o.outcome_class, o.quality_level, o.source_reference "
                "FROM outcomes o JOIN donors d ON d.donor_id = o.donor_id "
                f"WHERE o.prediction_id IN ({placeholders}) ORDER BY o.id",
                list(by_id),
            ).fetchall()
            for r in rows:
                by_id[r[0]].outcomes.append(StoredOutcome(r[1], r[2], r[3], r[4], bool(r[5]), *r[6:12]))
        return predictions

    # --- Profile and export ------------------------------------------------

    def evidence_profile(self, agent_id: Optional[str] = None) -> EvidenceProfile:
        """Объём, качество и независимость доказательств, по агенту или
        по всей базе. n_genomes считается по genome_hash наблюдений."""
        obs_filter, params = ("WHERE agent_id = ?", [agent_id]) if agent_id is not None else ("", [])
        n_obs, n_agents, n_genomes = self._conn.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT agent_id), COUNT(DISTINCT genome_hash) FROM observations {obs_filter}",
            params,
        ).fetchone()

        evidence = self.get_evidence(agent_id=agent_id)
        groups: Dict[str, int] = {}
        by_quality = {level: 0 for level in QUALITY_LEVELS}
        for e in evidence:
            groups[e.independence_group] = groups.get(e.independence_group, 0) + 1
            by_quality[e.quality_level] += 1

        predictions = self.get_predictions(agent_id)
        pred_filter = "WHERE p.agent_id = ?" if agent_id is not None else ""
        n_pred_obs, n_pred_agents, n_pred_genomes = self._conn.execute(
            "SELECT COUNT(DISTINCT p.observation_id), COUNT(DISTINCT p.agent_id), COUNT(DISTINCT o.genome_hash) "
            f"FROM predictions p JOIN observations o ON o.id = p.observation_id {pred_filter}",
            params,
        ).fetchone()
        return EvidenceProfile(
            agent_id=agent_id,
            n_observations=n_obs,
            n_agents=n_agents,
            n_genomes=n_genomes,
            n_evidence=len(evidence),
            n_donors=len({e.donor_id for e in evidence}),
            n_independence_groups=len(groups),
            independence_groups=groups,
            evidence_by_quality=by_quality,
            n_predictions=len(predictions),
            n_predictions_with_outcome=sum(1 for p in predictions if p.outcomes),
            n_verified_outcomes=sum(
                1 for p in predictions for o in p.outcomes if o.verification in ("human", "ground_truth")
            ),
            n_predicted_observations=n_pred_obs,
            n_predicted_agents=n_pred_agents,
            n_predicted_genomes=n_pred_genomes,
            n_duplicate_evidence=self._conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE fingerprint IS NULL"
                + (" AND observation_id IN (SELECT id FROM observations WHERE agent_id = ?)" if agent_id else ""),
                params,
            ).fetchone()[0],
            n_duplicate_outcomes=self._conn.execute(
                f"SELECT COUNT(*) FROM outcomes o JOIN predictions p ON p.id = o.prediction_id "
                f"WHERE o.fingerprint IS NULL {'AND p.agent_id = ?' if agent_id else ''}", params,
            ).fetchone()[0],
            n_duplicate_predictions=self._conn.execute(
                f"SELECT COALESCE(SUM(c - 1), 0) FROM (SELECT COUNT(*) AS c FROM predictions p {pred_filter} "
                f"GROUP BY observation_id, target, horizon HAVING COUNT(*) > 1)", params,
            ).fetchone()[0],
            outcomes_by_quality={
                level: self._conn.execute(
                    f"SELECT COUNT(*) FROM outcomes o JOIN predictions p ON p.id = o.prediction_id "
                    f"WHERE o.quality_level = ? AND o.fingerprint IS NOT NULL {'AND p.agent_id = ?' if agent_id else ''}",
                    [level] + params,
                ).fetchone()[0]
                for level in QUALITY_LEVELS
            },
            n_outcomes_without_class=self._conn.execute(
                f"SELECT COUNT(*) FROM outcomes o JOIN predictions p ON p.id = o.prediction_id "
                f"WHERE o.outcome_class IS NULL {'AND p.agent_id = ?' if agent_id else ''}", params,
            ).fetchone()[0],
        )

    def export_evidence_graph_json(self, path: str) -> str:
        """Доноры, доказательства, предсказания с исходами одним JSON.
        Наблюдения экспортируются отдельно, export_json()."""
        from dataclasses import asdict
        data = {
            "donors": [asdict(d) for d in self.list_donors()],
            "evidence": [asdict(e) for e in self.get_evidence()],
            "predictions": [asdict(p) for p in self.get_predictions()],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
