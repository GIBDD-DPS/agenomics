"""
drift.py — Drift Monitor методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.0

Отслеживает историю Trust Score одного агента во времени и определяет,
деградирует ли его поведение — вместо разовой статичной оценки.
Закрывает ограничение, зафиксированное в docs/METHODOLOGY.md:
"формула не учитывает исторические инциденты агента".
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

_DEGRADING_SLOPE_THRESHOLD = -3.0  # падение очков за один снимок
_MIN_SNAPSHOTS_FOR_TREND = 3


@dataclass
class ScoreSnapshot:
    timestamp: datetime
    score: float
    confidence: str = "High"


@dataclass
class DriftReport:
    agent_id: str
    snapshots_count: int
    trend: str  # "improving" / "stable" / "degrading" / "insufficient_data"
    slope: float
    latest_score: float
    earliest_score: float
    alert: bool
    alert_reason: Optional[str] = None


class DriftMonitor:
    """Хранит историю снимков Trust Score по agent_id и определяет тренд.

    Это НЕ база данных — состояние живёт в памяти процесса. Для
    продакшена нужна персистентность (файл/БД) на стороне пользователя
    библиотеки; DriftMonitor даёт только логику анализа тренда.
    """

    def __init__(self):
        self._history: Dict[str, List[ScoreSnapshot]] = {}

    def record(self, agent_id: str, score: float, confidence: str = "High",
               timestamp: Optional[datetime] = None) -> ScoreSnapshot:
        snap = ScoreSnapshot(timestamp=timestamp or datetime.now(timezone.utc), score=score, confidence=confidence)
        self._history.setdefault(agent_id, []).append(snap)
        return snap

    def history(self, agent_id: str) -> List[ScoreSnapshot]:
        return list(self._history.get(agent_id, []))

    def report(self, agent_id: str) -> DriftReport:
        snaps = self._history.get(agent_id, [])
        if not snaps:
            raise ValueError(f"Нет истории для агента '{agent_id}'")

        if len(snaps) < _MIN_SNAPSHOTS_FOR_TREND:
            return DriftReport(
                agent_id=agent_id, snapshots_count=len(snaps), trend="insufficient_data",
                slope=0.0, latest_score=snaps[-1].score, earliest_score=snaps[0].score,
                alert=False,
                alert_reason=(
                    f"Нужно минимум {_MIN_SNAPSHOTS_FOR_TREND} снимков для тренда, "
                    f"есть {len(snaps)}"
                ),
            )

        n = len(snaps)
        # Простая линейная оценка: (последний - первый) / число шагов между ними.
        # Не полноценная линейная регрессия — достаточно для тренда на малых выборках.
        slope = (snaps[-1].score - snaps[0].score) / (n - 1)

        if slope <= _DEGRADING_SLOPE_THRESHOLD:
            trend = "degrading"
        elif slope >= abs(_DEGRADING_SLOPE_THRESHOLD):
            trend = "improving"
        else:
            trend = "stable"

        alert = trend == "degrading"
        alert_reason = (
            f"Trust Score агента '{agent_id}' снижается в среднем на {abs(slope):.1f} "
            f"пунктов за снимок — рекомендуется ручная проверка."
            if alert else None
        )

        return DriftReport(
            agent_id=agent_id, snapshots_count=n, trend=trend, slope=round(slope, 2),
            latest_score=snaps[-1].score, earliest_score=snaps[0].score,
            alert=alert, alert_reason=alert_reason,
        )
