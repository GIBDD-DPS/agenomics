"""
drift.py — Drift Monitor методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.6.0

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


# ============================================================================
# DriftMonitor v2 (v0.6.0) — устраняет найденный бенчмарком недостаток v1:
# простая линейная эвристика (первый снимок vs последний) не обнаруживала
# слабую (mild) деградацию за разумное окно наблюдения.
#
# v2 добавляет: rolling window, EWMA, волатильность, baseline, явную
# классификацию тяжести (none/mild/moderate/severe/sudden), и обнаружение
# восстановления (recovery) — вместо плоского improving/stable/degrading.
#
# DriftMonitor (v1) сохранён без изменений — semver 0.x позволяет breaking
# changes, но замена работающего класса без необходимости — плохая практика.
# ============================================================================

_DEFAULT_BASELINE_WINDOW = 3
_DEFAULT_ROLLING_WINDOW = 8
_DEFAULT_EWMA_ALPHA = 0.3
_DEFAULT_MILD_THRESHOLD = 0.05      # относительное отклонение EWMA от baseline
_DEFAULT_MODERATE_THRESHOLD = 0.15
_DEFAULT_SEVERE_THRESHOLD = 0.30
_DEFAULT_SUDDEN_DROP_THRESHOLD = 15.0  # абсолютное падение за ОДИН шаг
_DEFAULT_RECOVERY_WINDOW = 3


@dataclass
class DriftReportV2:
    agent_id: str
    snapshots_count: int
    baseline: Optional[float]
    ewma: Optional[float]
    slope: float
    volatility: float
    severity: str  # "insufficient_data" / "none" / "mild" / "moderate" / "severe" / "sudden" / "volatile"
    alert: bool
    recovered: bool
    detail: str = ""


class DriftMonitorV2:
    """
    Улучшенный Drift Monitor: rolling window + EWMA + волатильность +
    явная классификация тяжести + обнаружение восстановления.

    Все пороги настраиваемые — калибровка на конкретных данных остаётся
    задачей пользователя библиотеки; значения по умолчанию откалиброваны
    на синтетических сценариях benchmark/scenarios.py (см. benchmark/BENCHMARKS.md).
    """

    def __init__(
        self,
        baseline_window: int = _DEFAULT_BASELINE_WINDOW,
        rolling_window: int = _DEFAULT_ROLLING_WINDOW,
        ewma_alpha: float = _DEFAULT_EWMA_ALPHA,
        mild_threshold: float = _DEFAULT_MILD_THRESHOLD,
        moderate_threshold: float = _DEFAULT_MODERATE_THRESHOLD,
        severe_threshold: float = _DEFAULT_SEVERE_THRESHOLD,
        sudden_drop_threshold: float = _DEFAULT_SUDDEN_DROP_THRESHOLD,
        recovery_window: int = _DEFAULT_RECOVERY_WINDOW,
        volatility_threshold: float = 6.0,
    ):
        self._history: Dict[str, List[ScoreSnapshot]] = {}
        self._baseline_window = baseline_window
        self._rolling_window = rolling_window
        self._ewma_alpha = ewma_alpha
        self._mild = mild_threshold
        self._moderate = moderate_threshold
        self._severe = severe_threshold
        self._sudden_drop = sudden_drop_threshold
        self._recovery_window = recovery_window
        self._volatility_threshold = volatility_threshold
        # Состояние "был ли alert раньше" — для корректного recovery detection
        # (не завязано на конкретную ширину окна, работает при любой длине истории).
        self._ever_alerted: Dict[str, bool] = {}

    def record(self, agent_id: str, score: float, confidence: str = "High",
               timestamp: Optional[datetime] = None) -> ScoreSnapshot:
        snap = ScoreSnapshot(timestamp=timestamp or datetime.now(timezone.utc), score=score, confidence=confidence)
        self._history.setdefault(agent_id, []).append(snap)
        return snap

    def history(self, agent_id: str) -> List[ScoreSnapshot]:
        return list(self._history.get(agent_id, []))

    @staticmethod
    def _count_sign_changes(diffs: List[float], eps: float = 1e-6) -> int:
        """Число смен знака в последовательности приращений. Колебание
        (oscillation) даёт много смен знака в окне; единичный устойчивый
        скачок (sudden) — не больше одной. Это и есть признак, отличающий
        их друг от друга при одинаково высокой волатильности окна."""
        changes = 0
        prev_sign = 0
        for d in diffs:
            if abs(d) < eps:
                continue
            sign = 1 if d > 0 else -1
            if prev_sign != 0 and sign != prev_sign:
                changes += 1
            prev_sign = sign
        return changes

    @staticmethod
    def _ewma_series(scores: List[float], alpha: float) -> List[float]:
        ewma = []
        for i, s in enumerate(scores):
            ewma.append(s if i == 0 else alpha * s + (1 - alpha) * ewma[-1])
        return ewma

    def report(self, agent_id: str) -> DriftReportV2:
        snaps = self._history.get(agent_id, [])
        n = len(snaps)
        if n == 0:
            raise ValueError(f"Нет истории для агента '{agent_id}'")

        scores = [s.score for s in snaps]

        if n < self._baseline_window:
            return DriftReportV2(
                agent_id=agent_id, snapshots_count=n, baseline=None, ewma=scores[-1],
                slope=0.0, volatility=0.0, severity="insufficient_data", alert=False,
                recovered=False,
                detail=f"Нужно минимум {self._baseline_window} снимков для baseline, есть {n}",
            )

        baseline = sum(scores[:self._baseline_window]) / self._baseline_window

        window = scores[-self._rolling_window:]
        ewma_series = self._ewma_series(window, self._ewma_alpha)
        current_ewma = ewma_series[-1]

        slope = (ewma_series[-1] - ewma_series[0]) / (len(ewma_series) - 1) if len(ewma_series) >= 2 else 0.0

        mean_window = sum(window) / len(window)
        volatility = (sum((x - mean_window) ** 2 for x in window) / len(window)) ** 0.5

        relative_deviation = (baseline - current_ewma) / baseline if baseline else 0.0

        raw_sudden = n >= 2 and (scores[-2] - scores[-1]) >= self._sudden_drop
        diffs = [window[i + 1] - window[i] for i in range(len(window) - 1)]
        sign_changes = self._count_sign_changes(diffs)

        if raw_sudden and volatility >= self._volatility_threshold and sign_changes >= 2:
            severity = "volatile"
        elif raw_sudden:
            severity = "sudden"
        elif relative_deviation >= self._severe:
            severity = "severe"
        elif relative_deviation >= self._moderate:
            severity = "moderate"
        elif relative_deviation >= self._mild:
            severity = "mild"
        else:
            severity = "none"

        alert = severity not in ("none",)

        recovered = False
        if alert:
            self._ever_alerted[agent_id] = True
        elif self._ever_alerted.get(agent_id, False):
            recovered = True
            self._ever_alerted[agent_id] = False

        detail = (
            f"baseline={baseline:.1f}, EWMA={current_ewma:.1f}, "
            f"отклонение={relative_deviation * 100:.1f}%, slope={slope:.2f}, "
            f"волатильность={volatility:.2f}"
        )

        return DriftReportV2(
            agent_id=agent_id, snapshots_count=n, baseline=round(baseline, 2),
            ewma=round(current_ewma, 2), slope=round(slope, 2), volatility=round(volatility, 2),
            severity=severity, alert=alert, recovered=recovered, detail=detail,
        )
