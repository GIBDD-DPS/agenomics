"""
ledger.py — Genome Ledger методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.0

Простой append-only реестр: хэш генома + результат аудита + дата.
Локальная in-memory реализация — прототип публичного реестра
верификации из roadmap. НЕ криптографически защищён от подмены
(это не блокчейн) — просто цепочка хэшей для базовой целостности
внутри одного процесса/файла.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .trust_score import AgentGenome, TrustResult


def _genome_hash(genome: AgentGenome) -> str:
    """Детерминированный хэш генома — по значениям полей, не по id объекта в памяти."""
    autonomy_value = genome.autonomy.value if hasattr(genome.autonomy, "value") else genome.autonomy
    payload = {
        "id": genome.id, "domain": genome.domain, "domains": genome.domains,
        "autonomy": autonomy_value,
        "transparency": genome.transparency, "bias_control": genome.bias_control,
        "data_safety": genome.data_safety, "drift_rate": genome.drift_rate,
        "has_ledger": genome.has_ledger, "role": genome.role,
        "risk_tolerance": genome.risk_tolerance, "social_style": genome.social_style,
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
    prev_hash: Optional[str] = None  # хэш предыдущей записи — цепочка целостности


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
        реестра — НЕ защищает от подмены самого файла/базы извне."""
        for i in range(1, len(self._entries)):
            if self._entries[i].prev_hash != self._entries[i - 1].genome_hash:
                return False
        return True

    def export_json(self) -> str:
        return json.dumps([asdict(e) for e in self._entries], ensure_ascii=False, indent=2)
