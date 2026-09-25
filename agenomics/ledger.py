# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
ledger.py. Genome Ledger методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab

Простой append-only реестр: хэш генома, результат аудита, дата.
Локальная in-memory реализация, прототип публичного реестра
верификации из roadmap. Не криптографически защищён от подмены
(это не блокчейн), просто цепочка хэшей для базовой целостности
внутри одного процесса или файла.

[v0.8.0] Genome Versioning: каждая запись знает, от какой версии генома
этого агента она произошла (parent_genome_hash), кто её создал
(created_by) и почему (change_reason). lineage() восстанавливает цепочку
версий генома, а не просто список аудитов.
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
                 confidence: str, timestamp: str, prev_hash: Optional[str],
                 parent_genome_hash: Optional[str] = None, created_by: Optional[str] = None,
                 change_reason: Optional[str] = None, genome_version: int = 1) -> str:
    """Хэш ВСЕЙ записи реестра, не только genome_hash.

    Раньше цепочка целостности связывала записи через genome_hash
    предыдущей записи, значит, изменение score/label/confidence/
    timestamp постфактум НЕ обязательно ломало цепочку, если сам
    genome_hash оставался прежним. Честная находка внешнего разбора,
    указанная дважды подряд. Теперь prev_hash ссылается на entry_hash
    предыдущей записи, а entry_hash покрывает все поля этой записи,
    так что изменение любого из них меняет entry_hash, а значит и
    цепочку целиком.

    С v0.8.0 хэш покрывает и поля версионирования: подменить постфактум
    parent_genome_hash, created_by или change_reason, не сломав
    verify_integrity(), так же нельзя, как score."""
    payload = {
        "prev_hash": prev_hash, "genome_hash": genome_hash, "agent_id": agent_id,
        "score": score, "label": label, "confidence": confidence, "timestamp": timestamp,
        "parent_genome_hash": parent_genome_hash, "created_by": created_by,
        "change_reason": change_reason, "genome_version": genome_version,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _entry_hash_of(entry: "LedgerEntry") -> str:
    return _entry_hash(
        entry.genome_hash, entry.agent_id, entry.score, entry.label,
        entry.confidence, entry.timestamp, entry.prev_hash,
        parent_genome_hash=entry.parent_genome_hash, created_by=entry.created_by,
        change_reason=entry.change_reason, genome_version=entry.genome_version,
    )


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
    # [v0.8.0] Genome Versioning
    parent_genome_hash: Optional[str] = None  # предыдущая, ОТЛИЧАЮЩАЯСЯ версия генома; None у первой
    created_by: Optional[str] = None          # кто создал эту версию (человек, пайплайн, extractor)
    change_reason: Optional[str] = None       # почему геном изменился
    genome_version: int = 1                   # порядковый номер версии генома у этого агента


# Отличает "parent_genome_hash не передан, вычислить автоматически" от
# "передан явно None" (например, версия создана с нуля, а не из прошлой).
_AUTO = object()


class GenomeLedger:
    """Append-only реестр записей аудита (локальная in-memory реализация)."""

    def __init__(self):
        self._entries: List[LedgerEntry] = []

    def record(
        self,
        genome: AgentGenome,
        result: TrustResult,
        created_by: Optional[str] = None,
        change_reason: Optional[str] = None,
        parent_genome_hash=_AUTO,
    ) -> LedgerEntry:
        """Добавляет запись аудита.

        parent_genome_hash по умолчанию вычисляется сам: если геном
        агента изменился по сравнению с его последней записью, родитель
        это genome_hash той записи, а genome_version растёт на 1. Если
        геном тот же (повторный аудит без изменений), запись наследует
        родителя и номер версии предыдущей: это та же версия, а не новая.
        Явный parent_genome_hash нужен, когда версия получена не из
        последней версии этого же агента (например, форк чужого генома
        или откат к старой версии); явный None означает "создан с нуля".

        created_by и change_reason никто не угадывает за вызывающий код:
        не переданы, значит None."""
        prev_entry_hash = self._entries[-1].entry_hash if self._entries else None
        genome_hash = _genome_hash(genome)
        timestamp = datetime.now(timezone.utc).isoformat()

        previous = next((e for e in reversed(self._entries) if e.agent_id == genome.id), None)
        is_same_version = previous is not None and previous.genome_hash == genome_hash
        if is_same_version:
            genome_version = previous.genome_version
            auto_parent = previous.parent_genome_hash
        else:
            genome_version = previous.genome_version + 1 if previous else 1
            auto_parent = previous.genome_hash if previous else None
        resolved_parent = auto_parent if parent_genome_hash is _AUTO else parent_genome_hash

        entry = LedgerEntry(
            genome_hash=genome_hash,
            agent_id=genome.id,
            score=result.score,
            label=result.label,
            confidence=result.confidence,
            timestamp=timestamp,
            prev_hash=prev_entry_hash,
            parent_genome_hash=resolved_parent,
            created_by=created_by,
            change_reason=change_reason,
            genome_version=genome_version,
        )
        entry.entry_hash = _entry_hash_of(entry)
        self._entries.append(entry)
        return entry

    def lineage(self, agent_id: str) -> List[LedgerEntry]:
        """Цепочка версий генома агента: первая запись каждой версии, в
        порядке появления. Повторные аудиты той же версии не дублируются,
        для них есть entries_for()."""
        versions: List[LedgerEntry] = []
        seen_versions = set()
        for entry in self.entries_for(agent_id):
            if entry.genome_version not in seen_versions:
                seen_versions.add(entry.genome_version)
                versions.append(entry)
        return versions

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
            if _entry_hash_of(entry) != entry.entry_hash:
                return False
        return True

    def export_json(self) -> str:
        return json.dumps([asdict(e) for e in self._entries], ensure_ascii=False, indent=2)
