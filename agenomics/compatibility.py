"""
compatibility.py — Compatibility Scorer методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.2.0

Отвечает на вопрос: сработается ли команда из нескольких ИИ-агентов?
Использует те же геномы (AgentGenome), что и TrustScorer, плюс два
дополнительных поля: risk_tolerance и social_style.

Логика:
  1. Совместимость считается по 4 осям: этика, риск-толерантность,
     социальный стиль, подотчётность.
  2. Этическое расхождение — самое опасное: превышение порога даёт
     жёсткий потолок Compatibility Score ≤ 50 (по аналогии с потолком
     автономности в TrustScorer — единый принцип методологии).
  3. Для команды > 2 агентов считается средняя совместимость по всем
     парам + явно выделяется самая слабая пара (узкое место команды).
  4. Как и в TrustScorer — отсутствие данных не завышает оценку.
"""

from dataclasses import dataclass, field
from itertools import combinations
from typing import List, Optional, Tuple

from .trust_score import AgentGenome

_ETHICS_CONFLICT_THRESHOLD = 40   # разница bias_control, после которой применяется потолок
_ETHICS_CONFLICT_CAP = 50

_WEIGHTS = {
    "ethics": 0.35,
    "risk_tolerance": 0.25,
    "social_style": 0.20,
    "accountability": 0.20,
}


def _axis_gap_score(a: Optional[float], b: Optional[float]) -> Tuple[float, bool]:
    """
    Превращает разницу между двумя значениями оси (0-100) в оценку
    совместимости по этой оси (0-100, где 100 = полное совпадение).
    Возвращает (score, insufficient_info).
    """
    if a is None or b is None:
        return 50.0, True  # нейтрально, не завышаем
    gap = abs(a - b)
    return max(0.0, 100.0 - gap), False


@dataclass
class PairCompatibilityResult:
    agent_a: str
    agent_b: str
    score: float
    breakdown: dict = field(default_factory=dict)
    insufficient_axes: List[str] = field(default_factory=list)
    capped_reason: Optional[str] = None


@dataclass
class TeamCompatibilityResult:
    average_score: float
    pairs: List[PairCompatibilityResult] = field(default_factory=list)
    weakest_pair: Optional[PairCompatibilityResult] = None


class CompatibilityScorer:
    """Вычисляет совместимость пары или команды агентов."""

    def score_pair(self, a: AgentGenome, b: AgentGenome) -> PairCompatibilityResult:
        insufficient = []

        ethics_score, eth_insuff = _axis_gap_score(a.bias_control, b.bias_control)
        risk_score, risk_insuff = _axis_gap_score(a.risk_tolerance, b.risk_tolerance)
        social_score, soc_insuff = _axis_gap_score(a.social_style, b.social_style)
        acc_score, acc_insuff = _axis_gap_score(a.accountability, b.accountability)

        for name, insuff in [
            ("ethics", eth_insuff), ("risk_tolerance", risk_insuff),
            ("social_style", soc_insuff), ("accountability", acc_insuff),
        ]:
            if insuff:
                insufficient.append(name)

        breakdown = {
            "ethics": ethics_score,
            "risk_tolerance": risk_score,
            "social_style": social_score,
            "accountability": acc_score,
        }

        weighted = sum(breakdown[axis] * w for axis, w in _WEIGHTS.items())

        capped_reason = None
        ethics_gap = (
            abs(a.bias_control - b.bias_control)
            if a.bias_control is not None and b.bias_control is not None
            else None
        )
        if ethics_gap is not None and ethics_gap > _ETHICS_CONFLICT_THRESHOLD and weighted > _ETHICS_CONFLICT_CAP:
            weighted = _ETHICS_CONFLICT_CAP
            capped_reason = (
                f"Этическое расхождение между агентами ({ethics_gap:.0f} пунктов "
                f"bias_control) превышает порог {_ETHICS_CONFLICT_THRESHOLD} — "
                f"Compatibility Score не может быть выше {_ETHICS_CONFLICT_CAP}, "
                f"независимо от совпадения по другим осям."
            )

        return PairCompatibilityResult(
            agent_a=a.id,
            agent_b=b.id,
            score=round(weighted, 1),
            breakdown=breakdown,
            insufficient_axes=insufficient,
            capped_reason=capped_reason,
        )

    def score_team(self, agents: List[AgentGenome]) -> TeamCompatibilityResult:
        if len(agents) < 2:
            raise ValueError("Для оценки совместимости нужно минимум 2 агента.")

        pairs = [self.score_pair(a, b) for a, b in combinations(agents, 2)]
        average = round(sum(p.score for p in pairs) / len(pairs), 1)
        weakest = min(pairs, key=lambda p: p.score)

        return TeamCompatibilityResult(
            average_score=average,
            pairs=pairs,
            weakest_pair=weakest,
        )
