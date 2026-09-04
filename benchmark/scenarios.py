"""
scenarios.py — синтетические сценарии для Agenomics Benchmark Suite.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.6.0

Все сценарии здесь — синтетические, с заранее известным "правильным"
порядком/ответом, сконструированным человеком, а не собранным из
реальных агентов. Это тесты внутренней логики формулы, а не выборка
реального мира — см. предупреждение в benchmark/__init__.py.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from agenomics import AgentGenome


def quality_spectrum_genomes(n: int = 21) -> List[Tuple[AgentGenome, float]]:
    """
    Генерирует n геномов, равномерно покрывающих спектр от "очень плохого"
    до "отличного" агента по всем 5 осям одновременно, вместе с известным
    "истинным рангом качества" intended_quality (0.0 = худший, 1.0 = лучший).

    Используется для проверки Trust Calibration: если методология
    последовательна, итоговый Trust Score должен монотонно расти вместе
    с intended_quality.
    """
    result = []
    for i in range(n):
        intended_quality = i / (n - 1)  # 0.0 .. 1.0
        value = 10 + intended_quality * 85  # от 10 до 95 по всем осям синхронно
        genome = AgentGenome(
            id=f"quality-{i}",
            domain="content",  # TIER_1, чтобы не мешал tier-множитель
            autonomy="advisory",  # чтобы не мешал потолок автономности
            transparency=value,
            bias_control=value,
            data_safety=value,
            drift_rate=1 - (intended_quality),  # выше качество -> ниже drift_rate
            has_ledger=intended_quality > 0.5,  # порог, а не непрерывная функция — намеренно
        )
        result.append((genome, intended_quality))
    return result


def drift_rate_spectrum_genomes(n: int = 21) -> List[Tuple[AgentGenome, float]]:
    """
    То же самое, но меняется ТОЛЬКО drift_rate — остальные оси фиксированы.
    Используется для проверки Behavioral Predictability: Predictability
    должна монотонно убывать при росте drift_rate, изолированно от
    остальных осей.
    """
    result = []
    for i in range(n):
        drift_rate = i / (n - 1)  # 0.0 .. 1.0
        genome = AgentGenome(
            id=f"drift-{i}",
            domain="content",
            autonomy="advisory",
            transparency=80, bias_control=80, data_safety=80,
            drift_rate=drift_rate,
            has_ledger=True,
        )
        result.append((genome, drift_rate))
    return result


@dataclass
class CompatibilityCase:
    genome_a: AgentGenome
    genome_b: AgentGenome
    label: str  # "compatible" | "conflicting"
    description: str


def compatibility_ground_truth_cases() -> List[CompatibilityCase]:
    """
    Пары агентов с заведомо известным ожидаемым результатом (сконструировано
    вручную, не из реальных инцидентов). Используется для проверки
    Compatibility Accuracy: должны ли "conflicting" пары получать
    систематически более низкий Compatibility Score, чем "compatible".
    """
    cases = []

    cases.append(CompatibilityCase(
        genome_a=AgentGenome(id="a1", bias_control=90, risk_tolerance=40, social_style=50, has_ledger=True),
        genome_b=AgentGenome(id="a2", bias_control=88, risk_tolerance=45, social_style=55, has_ledger=True),
        label="compatible",
        description="Похожие агенты по всем осям — эталонная совместимая пара",
    ))
    cases.append(CompatibilityCase(
        genome_a=AgentGenome(id="b1", bias_control=95, risk_tolerance=50, social_style=50, has_ledger=True),
        genome_b=AgentGenome(id="b2", bias_control=30, risk_tolerance=50, social_style=50, has_ledger=True),
        label="conflicting",
        description="Резкое этическое расхождение (bias_control 95 vs 30) — эталонный конфликт",
    ))
    cases.append(CompatibilityCase(
        genome_a=AgentGenome(id="c1", bias_control=85, risk_tolerance=10, social_style=90, has_ledger=True),
        genome_b=AgentGenome(id="c2", bias_control=85, risk_tolerance=95, social_style=5, has_ledger=False),
        label="conflicting",
        description="Расхождение по риск-толерантности, стилю и подотчётности одновременно (без ролей)",
    ))
    cases.append(CompatibilityCase(
        genome_a=AgentGenome(id="d1", bias_control=82, risk_tolerance=60, social_style=60, has_ledger=True),
        genome_b=AgentGenome(id="d2", bias_control=80, risk_tolerance=55, social_style=65, has_ledger=True),
        label="compatible",
        description="Небольшие расхождения по всем осям, ничего критического",
    ))
    return cases


def drift_timeseries_with_known_degradation(
    degrade_at_step: int = 5, length: int = 10, severity: str = "moderate"
) -> Tuple[List[float], int]:
    """
    Синтетическая временная последовательность Trust Score с ЗАРАНЕЕ
    ИЗВЕСТНЫМ шагом, на котором начинается деградация (degrade_at_step).

    Возвращает (scores, degrade_at_step) — scores стабильны до
    degrade_at_step, затем падают с заданной "тяжестью".

    Используется для проверки Drift Detection: сколько дополнительных
    шагов после реального начала деградации нужно DriftMonitor, чтобы
    поднять alert=True (задержка обнаружения).
    """
    severity_drop = {"mild": 2.0, "moderate": 5.0, "severe": 10.0}[severity]
    scores = []
    base = 88.0
    for step in range(length):
        if step < degrade_at_step:
            scores.append(base)
        else:
            steps_since_degrade = step - degrade_at_step + 1
            scores.append(max(0.0, base - severity_drop * steps_since_degrade))
    return scores, degrade_at_step


# ============================================================================
# Расширенные сценарии Drift Monitor v2 (v0.6.0) — 7 типов вместо трёх
# уровней тяжести v0.1. Все сценарии детерминированы (синус вместо random)
# для воспроизводимости бенчмарка.
# ============================================================================

import math


def drift_scenario_no_drift(length: int = 20, base: float = 85.0, noise: float = 1.5) -> List[float]:
    """Стабильный агент с небольшим шумом, БЕЗ реальной деградации.
    Используется для проверки false positive rate — DriftMonitor не должен
    поднимать alert на обычный шум."""
    return [round(base + noise * math.sin(i * 1.7), 2) for i in range(length)]


def drift_scenario_mild(length: int = 20, base: float = 85.0, degrade_at: int = 5, total_drop: float = 8.0) -> List[float]:
    """Слабая, но устойчивая деградация — именно то, что v1 DriftMonitor
    не обнаруживал вовсе за 15 шагов (см. benchmark/README.md, находка v0.1)."""
    scores = []
    remaining_steps = length - degrade_at
    for i in range(length):
        if i < degrade_at:
            scores.append(base)
        else:
            progress = (i - degrade_at + 1) / remaining_steps
            scores.append(round(base - total_drop * progress, 2))
    return scores


def drift_scenario_moderate(length: int = 20, base: float = 85.0, degrade_at: int = 5, total_drop: float = 22.0) -> List[float]:
    return drift_scenario_mild(length, base, degrade_at, total_drop)


def drift_scenario_severe(length: int = 20, base: float = 85.0, degrade_at: int = 5, total_drop: float = 45.0) -> List[float]:
    return drift_scenario_mild(length, base, degrade_at, total_drop)


def drift_scenario_sudden(length: int = 20, base: float = 85.0, drop_at: int = 10, drop_amount: float = 35.0) -> List[float]:
    """Одномоментный резкий провал НА ОДНОМ шаге (не постепенный) —
    отдельный класс от градуальной деградации, должен обнаруживаться мгновенно."""
    scores = []
    for i in range(length):
        if i < drop_at:
            scores.append(base)
        else:
            scores.append(base - drop_amount)
    return scores


def drift_scenario_recovery(
    length: int = 30, base: float = 85.0, degrade_at: int = 5,
    total_drop: float = 25.0, recover_at: int = 18,
) -> List[float]:
    """Деградация, затем ПОЛНОЕ восстановление до baseline — проверяет
    recovery detection, а не только сам факт деградации."""
    scores = []
    degrade_steps = recover_at - degrade_at
    for i in range(length):
        if i < degrade_at:
            scores.append(base)
        elif i < recover_at:
            progress = (i - degrade_at + 1) / degrade_steps
            scores.append(round(base - total_drop * progress, 2))
        else:
            scores.append(base)  # мгновенное возвращение к норме после recover_at
    return scores


def drift_scenario_oscillation(length: int = 20, base: float = 85.0, amplitude: float = 15.0, period: int = 4) -> List[float]:
    """Сильные колебания БЕЗ чёткого тренда деградации — проверяет, что
    высокая волатильность сама по себе не должна ложно давать 'degrading'."""
    return [round(base + amplitude * math.sin(2 * math.pi * i / period), 2) for i in range(length)]


DRIFT_SCENARIOS_V2 = {
    "no_drift": drift_scenario_no_drift,
    "mild": drift_scenario_mild,
    "moderate": drift_scenario_moderate,
    "severe": drift_scenario_severe,
    "sudden": drift_scenario_sudden,
    "recovery": drift_scenario_recovery,
    "oscillation": drift_scenario_oscillation,
}


# ============================================================================
# Расширенный Compatibility ground truth (v0.6.0) — систематическая
# генерация вместо 4 ручных случаев v0.1. Детерминированный перебор
# параметров (не random) — воспроизводимость бенчмарка не нарушается.
# ============================================================================

@dataclass
class CompatibilityCaseV2:
    genome_a: AgentGenome
    genome_b: AgentGenome
    category: str
    expected_label: str  # "compatible" | "conflicting" | "ambiguous"
    description: str


# Категории и их характерные разрывы (gap) по осям — экспертная
# конструкция, не выборка из реальных данных (как и в v0.1).
_COMPAT_CATEGORY_SPECS = {
    "obvious_compatible": dict(bias_gap=(0, 5), risk_gap=(0, 5), social_gap=(0, 5), expected="compatible"),
    "compatible": dict(bias_gap=(5, 15), risk_gap=(5, 15), social_gap=(5, 15), expected="compatible"),
    "near_threshold": dict(bias_gap=(35, 45), risk_gap=(10, 20), social_gap=(10, 20), expected="ambiguous"),
    "neutral": dict(bias_gap=(15, 30), risk_gap=(15, 30), social_gap=(15, 30), expected="ambiguous"),
    "mild_conflict": dict(bias_gap=(20, 35), risk_gap=(30, 50), social_gap=(30, 50), expected="conflicting"),
    "strong_conflict": dict(bias_gap=(20, 35), risk_gap=(60, 90), social_gap=(60, 90), expected="conflicting"),
    "ethical_conflict": dict(bias_gap=(45, 70), risk_gap=(10, 20), social_gap=(10, 20), expected="conflicting"),
    "high_risk_combination": dict(bias_gap=(25, 40), risk_gap=(40, 60), social_gap=(50, 70), expected="conflicting"),
}


def _make_pair_with_gap(base: float, bias_gap: float, risk_gap: float, social_gap: float,
                         id_a: str, id_b: str, has_ledger_a: bool = True, has_ledger_b: bool = True,
                         role_a: Optional[str] = None, role_b: Optional[str] = None) -> Tuple[AgentGenome, AgentGenome]:
    genome_a = AgentGenome(
        id=id_a, bias_control=min(100, base + bias_gap / 2), risk_tolerance=min(100, base + risk_gap / 2),
        social_style=min(100, base + social_gap / 2), has_ledger=has_ledger_a, role=role_a,
    )
    genome_b = AgentGenome(
        id=id_b, bias_control=max(0, base - bias_gap / 2), risk_tolerance=max(0, base - risk_gap / 2),
        social_style=max(0, base - social_gap / 2), has_ledger=has_ledger_b, role=role_b,
    )
    return genome_a, genome_b


def generate_compatibility_ground_truth(cases_per_category: int = 30) -> List[CompatibilityCaseV2]:
    """
    Генерирует cases_per_category * 9 категорий случаев (по умолчанию 270,
    в запрошенном диапазоне 100-500). Внутри категории gap варьируется
    систематически по диапазону, а базовое значение (base) сдвигается по
    всему допустимому диапазону 20-80, чтобы покрыть не только крайние,
    но и средние абсолютные уровни осей.
    """
    cases = []
    idx = 0
    for category, spec in _COMPAT_CATEGORY_SPECS.items():
        for i in range(cases_per_category):
            t = i / max(1, cases_per_category - 1)  # 0.0 .. 1.0
            base = 20 + t * 60  # 20 .. 80
            bias_gap = spec["bias_gap"][0] + t * (spec["bias_gap"][1] - spec["bias_gap"][0])
            risk_gap = spec["risk_gap"][0] + t * (spec["risk_gap"][1] - spec["risk_gap"][0])
            social_gap = spec["social_gap"][0] + t * (spec["social_gap"][1] - spec["social_gap"][0])

            genome_a, genome_b = _make_pair_with_gap(
                base, bias_gap, risk_gap, social_gap,
                id_a=f"{category}-{idx}-a", id_b=f"{category}-{idx}-b",
            )
            cases.append(CompatibilityCaseV2(
                genome_a=genome_a, genome_b=genome_b, category=category,
                expected_label=spec["expected"],
                description=f"{category}: bias_gap≈{bias_gap:.0f}, risk_gap≈{risk_gap:.0f}, social_gap≈{social_gap:.0f}",
            ))
            idx += 1

    # Отдельная категория role_complementarity — большой risk_gap, но с
    # ролями executor/reviewer, где по методологии этот gap НЕ штрафуется.
    # Проверяет, что role-aware логика реально работает, а не просто
    # заявлена в README.
    for i in range(cases_per_category):
        t = i / max(1, cases_per_category - 1)
        base = 20 + t * 60
        genome_a, genome_b = _make_pair_with_gap(
            base, bias_gap=5, risk_gap=70, social_gap=10,
            id_a=f"role_complementarity-{i}-a", id_b=f"role_complementarity-{i}-b",
            role_a="reviewer", role_b="executor",
        )
        cases.append(CompatibilityCaseV2(
            genome_a=genome_a, genome_b=genome_b, category="role_complementarity",
            expected_label="compatible",
            description="Большой risk_tolerance gap, но роли executor/reviewer нейтрализуют штраф",
        ))

    return cases
