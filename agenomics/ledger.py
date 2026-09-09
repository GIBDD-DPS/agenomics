"""
ledger.py. Genome Ledger методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.7.10

Простой append-only реестр: хэш генома, результат аудита, дата.
Локальная in-memory реализация, прототип публичного реестра
верификации из roadmap. Не криптографически защищён от подмены
(это не блокчейн), просто цепочка хэшей для базовой целостности
внутри одного процесса или файла.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .trust_score import AgentGenome, TrustResult


def _genome_hash(genome: AgentGenome) -> str:
    """Детерминированный хэш генома, по всем полям датакласса, а не по
    id объекта в памяти.

    Раньше здесь был вручную поддерживаемый список полей, и он не
    включал axis_confidence, accountability_override, tier_override,
    которые появились в AgentGenome позже исходной версии этой функции.
    Из-за этого два генома, различающихся только этими полями, получали
    одинаковый хэш, честная находка внешнего разбора. Использование
    dataclasses.asdict() автоматически охватывает любые текущие и
    будущие поля AgentGenome, без необходимости обновлять эту функцию
    при каждом новом поле."""
    payload = asdict(genome)
    raw = json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        default=lambda o: getattr(o, "value", str(o)),  # Enum -> .value, прочее -> str
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _entry_hash(genome_hash: str, agent_id: str, score: float, label: str,
                 confidence: str, timestamp: str, prev_hash: Optional[str]) -> str:
    """Хэш ВСЕЙ записи реестра, не только genome_hash.

    Раньше цепочка целостности связывала записи через genome_hash
    предыдущей записи, значит, изменение score/label/confidence/
    timestamp постфактум НЕ обязательно ломало цепочку, если сам
    genome_hash оставался прежним. Честная находка внешнего разбора,
    указанная дважды подряд. Теперь prev_hash ссылается на entry_hash
    предыдущей записи, а entry_hash покрывает все поля этой записи,
    так что изменение любого из них меняет entry_hash, а значит и
    цепочку целиком."""
    payload = {
        "prev_hash": prev_hash, "genome_hash": genome_hash, "agent_id": agent_id,
        "score": score, "label": label, "confidence": confidence, "timestamp": timestamp,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class LedgerEntry:
    genome_hash: str
    agent_id: str
    score: float
    label: str
    confidence: str
    timestamp: str
    prev_hash: Optional[str] = None  # entry_hash предыдущей записи, не её genome_hash
    entry_hash: str = ""  # хэш этой записи целиком, вычисляется в record()


class GenomeLedger:
    """Append-only реестр записей аудита (локальная in-memory реализация)."""

    def __init__(self):
        self._entries: List[LedgerEntry] = []

    def record(self, genome: AgentGenome, result: TrustResult) -> LedgerEntry:
        prev_entry_hash = self._entries[-1].entry_hash if self._entries else None
        genome_hash = _genome_hash(genome)
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = LedgerEntry(
            genome_hash=genome_hash,
            agent_id=genome.id,
            score=result.score,
            label=result.label,
            confidence=result.confidence,
            timestamp=timestamp,
            prev_hash=prev_entry_hash,
            entry_hash=_entry_hash(
                genome_hash, genome.id, result.score, result.label,
                result.confidence, timestamp, prev_entry_hash,
            ),
        )
        self._entries.append(entry)
        return entry

    def entries_for(self, agent_id: str) -> List[LedgerEntry]:
        return [e for e in self._entries if e.agent_id == agent_id]

    def verify_integrity(self) -> bool:
        """Проверяет две вещи, не одну: (1) что prev_hash каждой записи
        совпадает с entry_hash предыдущей (обнаруживает удаление или
        перестановку записей), и (2) что entry_hash каждой записи всё
        ещё соответствует её реальным полям (обнаруживает изменение
        score/label/confidence/timestamp постфактум, даже если сам
        genome_hash не менялся). Не защищает от подмены самого файла/
        базы извне, это по-прежнему честно локальный in-memory реестр."""
        for i, entry in enumerate(self._entries):
            expected_prev = self._entries[i - 1].entry_hash if i > 0 else None
            if entry.prev_hash != expected_prev:
                return False
            recomputed = _entry_hash(
                entry.genome_hash, entry.agent_id, entry.score, entry.label,
                entry.confidence, entry.timestamp, entry.prev_hash,
            )
            if recomputed != entry.entry_hash:
                return False
        return True

    def export_json(self) -> str:
        return json.dumps([asdict(e) for e in self._entries], ensure_ascii=False, indent=2)
