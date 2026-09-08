"""
ledger.py. Genome Ledger методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.7.5

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


@dataclass
class LedgerEntry:
    genome_hash: str
    agent_id: str
    score: float
    label: str
    confidence: str
    timestamp: str
    prev_hash: Optional[str] = None  # хэш предыдущей записи, цепочка целостности


class GenomeLedger:
    """Append-only реестр записей аудита (локальная in-memory реализация)."""

    def __init__(self):
        self._entries: List[LedgerEntry] = []

    def record(self, genome: AgentGenome, result: TrustResult) -> LedgerEntry:
        prev_hash = self._entries[-1].genome_hash if self._entries else None
        entry = LedgerEntry(
            genome_hash=_genome_hash(genome),
            agent_id=genome.id,
            score=result.score,
            label=result.label,
            confidence=result.confidence,
            timestamp=datetime.now(timezone.utc).isoformat(),
            prev_hash=prev_hash,
        )
        self._entries.append(entry)
        return entry

    def entries_for(self, agent_id: str) -> List[LedgerEntry]:
        return [e for e in self._entries if e.agent_id == agent_id]

    def verify_integrity(self) -> bool:
        """Проверяет непрерывность цепочки prev_hash. Обнаруживает случайное
        или намеренное удаление/перестановку записей внутри одного экземпляра
        реестра. Не защищает от подмены самого файла/базы извне."""
        for i in range(1, len(self._entries)):
            if self._entries[i].prev_hash != self._entries[i - 1].genome_hash:
                return False
        return True

    def export_json(self) -> str:
        return json.dumps([asdict(e) for e in self._entries], ensure_ascii=False, indent=2)
