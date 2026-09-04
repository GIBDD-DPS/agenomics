"""
scenarios.py — синтетические сценарии для Agenomics Benchmark Suite.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.5.0

Все сценарии здесь — синтетические, с заранее известным "правильным"
порядком/ответом, сконструированным человеком, а не собранным из
реальных агентов. Это тесты внутренней логики формулы, а не выборка
реального мира — см. предупреждение в benchmark/__init__.py.
"""

from dataclasses import dataclass
from typing import List, Tuple

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
