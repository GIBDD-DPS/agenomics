"""
per_axis_drift.py. Per-Axis Drift Monitoring.

Автор: Dm.Andreyanov
Проект: Prizolov Lab

DriftMonitorV2 (drift.py) уже универсален по конструкции: он принимает
любой числовой score, привязанный к произвольному ключу agent_id. Этот
модуль использует его же, не дублируя логику, применяя его к каждой оси
Trust Score отдельно (bias_control, transparency и т.д.), а не только к
итоговому агрегированному score.

Мотивация: разные оси по своей природе имеют разную "нормальную"
изменчивость. Bias Control обычно должен быть стабильным, его дрейф
почти всегда сигнал реальной проблемы. Transparency может колебаться
сильнее без что-то плохого. BASELINE_VOLATILITY_BY_AXIS ниже - это
экспертная эвристика (как и веса формулы), не результат статистического
анализа реальных данных. Используется как более мягкий или строгий порог
чувствительности per-axis DriftMonitorV2, а не как отдельная модель.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from .drift import DriftMonitorV2, DriftReportV2

# Экспертные ожидания "нормальной" волатильности по осям (0-100 шкала).
# Ниже -> более жёсткий mild_threshold (менее терпим к колебаниям).
# Выше -> более мягкий (терпимее к естественному разбросу).
BASELINE_VOLATILITY_BY_AXIS: Dict[str, float] = {
    "transparency": 0.08,     # относительно терпим к колебаниям
    "bias_control": 0.04,     # должен быть стабильным, дрейф здесь тревожнее
    "data_safety": 0.04,      # аналогично, безопасность не должна "гулять"
    "predictability": 0.06,
    "accountability": 0.05,
}
_DEFAULT_MILD_THRESHOLD = 0.05  # значение по умолчанию в DriftMonitorV2


class PerAxisDriftMonitor:
    """
    Держит по одному DriftMonitorV2 на каждую ось Trust Score для каждого
    агента, с порогом чувствительности, откалиброванным по
    BASELINE_VOLATILITY_BY_AXIS. Не новая модель дрейфа, а обёртка над уже
    протестированным DriftMonitorV2 (см. tests/test_drift_v2.py).
    """

    def __init__(self, baseline_volatility: Optional[Dict[str, float]] = None):
        self._baseline_volatility = baseline_volatility or BASELINE_VOLATILITY_BY_AXIS
        self._monitors: Dict[str, DriftMonitorV2] = {}

    def _key(self, agent_id: str, axis: str) -> str:
        return f"{agent_id}::{axis}"

    def _monitor_for(self, agent_id: str, axis: str) -> DriftMonitorV2:
        key = self._key(agent_id, axis)
        if key not in self._monitors:
            mild_threshold = self._baseline_volatility.get(axis, _DEFAULT_MILD_THRESHOLD)
            # Масштабируем moderate/severe в тех же пропорциях, что и
            # дефолты DriftMonitorV2 (0.05/0.15/0.30 -> ×3, ×6). Без этого
            # переопределение только mild_threshold ничего не меняло бы:
            # более мягкая ось всё равно попадала бы под старый (строгий)
            # moderate_threshold=0.15 раньше, чем добирается до mild.
            # Реальный баг, найденный при тестировании этого модуля.
            self._monitors[key] = DriftMonitorV2(
                mild_threshold=mild_threshold,
                moderate_threshold=mild_threshold * 3,
                severe_threshold=mild_threshold * 6,
            )
        return self._monitors[key]

    def record(self, agent_id: str, breakdown: Dict[str, float]) -> None:
        """Записывает снимок разбивки по осям (TrustResult.breakdown)
        одним вызовом. Под капотом это N вызовов DriftMonitorV2.record()."""
        for axis, value in breakdown.items():
            self._monitor_for(agent_id, axis).record(agent_id, value)

    def report(self, agent_id: str, axis: str) -> DriftReportV2:
        return self._monitor_for(agent_id, axis).report(agent_id)

    def report_all_axes(self, agent_id: str, axes: Optional[list] = None) -> Dict[str, DriftReportV2]:
        """Отчёт по всем осям, для которых уже есть история (или по
        явно переданному списку axes)."""
        axes_to_check = axes or [
            key.split("::", 1)[1] for key in self._monitors if key.startswith(f"{agent_id}::")
        ]
        return {axis: self.report(agent_id, axis) for axis in axes_to_check}

    def weakest_axis(self, agent_id: str) -> Optional[str]:
        """Возвращает ось с самой серьёзной деградацией (если есть хотя бы
        одна с alert=True), иначе None. Полезно для "куда смотреть в первую
        очередь", когда деградирует не всё сразу, а конкретная ось."""
        reports = self.report_all_axes(agent_id)
        severity_rank = {"none": 0, "insufficient_data": 0, "mild": 1, "volatile": 2, "moderate": 3, "severe": 4, "sudden": 5}
        alerting = {axis: r for axis, r in reports.items() if r.alert}
        if not alerting:
            return None
        return max(alerting, key=lambda a: severity_rank.get(alerting[a].severity, 0))
