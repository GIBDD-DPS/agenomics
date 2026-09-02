"""
compatibility.py — Compatibility Scorer методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.3.0

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

Улучшения v0.3:
  5. Настраиваемые профили весов ("default" / "safety_critical").
  6. Роли агентов: расхождение risk_tolerance между агентами с ролями
     "executor" и "reviewer" — не штрафуется, а засчитывается как
     полная совместимость. Осторожный ревьюер при рискованном
     исполнителе — осознанный чек-баланс, а не признак конфликта.
  7. Confidence — явная уверенность в оценке, отдельно от score.
"""

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from .trust_score import AgentGenome, AGENOMICS_ATTRIBUTION

_ETHICS_CONFLICT_THRESHOLD = 40   # разница bias_control, после которой применяется потолок
_ETHICS_CONFLICT_CAP = 50

DEFAULT_COMPAT_WEIGHTS: Dict[str, float] = {
    "ethics": 0.35,
    "risk_tolerance": 0.25,
    "social_style": 0.20,
    "accountability": 0.20,
}

# Профиль для команд, где хотя бы один агент в TIER 3 (финансы, здоровье,
# право) — этика весит ещё больше, а стиль общения меньше.
COMPAT_WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "default": DEFAULT_COMPAT_WEIGHTS,
    "safety_critical": {
        "ethics": 0.50,
        "risk_tolerance": 0.20,
        "social_style": 0.10,
        "accountability": 0.20,
    },
}

_WEIGHT_SUM_TOLERANCE = 0.001

# [v0.3] Пары ролей, для которых расхождение risk_tolerance — это дизайн,
# а не проблема: осторожный "reviewer", проверяющий рискованного
# "executor", специально должен иметь другую риск-толерантность.
_COMPLEMENTARY_ROLE_PAIRS = {
    frozenset({"executor", "reviewer"}),
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


def _is_complementary_pair(a: AgentGenome, b: AgentGenome) -> bool:
    if not a.role or not b.role:
        return False
    return frozenset({a.role, b.role}) in _COMPLEMENTARY_ROLE_PAIRS


@dataclass
class PairCompatibilityResult:
    agent_a: str
    agent_b: str
    score: float
    breakdown: dict = field(default_factory=dict)
    insufficient_axes: List[str] = field(default_factory=list)
    capped_reason: Optional[str] = None
    # [v0.3]
    confidence: str = "High"
    confidence_ratio: float = 1.0
    complementary_roles: bool = False  # True, если сработала role-aware логика
    attribution: str = AGENOMICS_ATTRIBUTION


@dataclass
class TeamCompatibilityResult:
    average_score: float
    pairs: List[PairCompatibilityResult] = field(default_factory=list)
    weakest_pair: Optional[PairCompatibilityResult] = None


class CompatibilityScorer:
    """Вычисляет совместимость пары или команды агентов."""

    def __init__(self, weight_profile: str = "default", weights: Optional[Dict[str, float]] = None):
        if weights is not None:
            resolved = weights
        else:
            if weight_profile not in COMPAT_WEIGHT_PROFILES:
                raise ValueError(
                    f"Неизвестный weight_profile '{weight_profile}'. "
                    f"Доступные: {list(COMPAT_WEIGHT_PROFILES.keys())}"
                )
            resolved = COMPAT_WEIGHT_PROFILES[weight_profile]

        total = sum(resolved.values())
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"Сумма весов должна быть 1.0, получено {total:.4f}")

        self._weights = resolved

    def score_pair(self, a: AgentGenome, b: AgentGenome) -> PairCompatibilityResult:
        insufficient = []
        complementary = _is_complementary_pair(a, b)

        ethics_score, eth_insuff = _axis_gap_score(a.bias_control, b.bias_control)

        if complementary:
            # Роли специально предполагают разную риск-толерантность —
            # это не недостаток совместимости, а осознанный дизайн команды.
            risk_score, risk_insuff = 100.0, False
        else:
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

        weighted = sum(breakdown[axis] * w for axis, w in self._weights.items())

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

        confidence_ratio = 1 - (len(insufficient) / len(breakdown))
        confidence = self._confidence_label(confidence_ratio)

        return PairCompatibilityResult(
            agent_a=a.id,
            agent_b=b.id,
            score=round(weighted, 1),
            breakdown=breakdown,
            insufficient_axes=insufficient,
            capped_reason=capped_reason,
            confidence=confidence,
            confidence_ratio=round(confidence_ratio, 2),
            complementary_roles=complementary,
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

    @staticmethod
    def _confidence_label(ratio: float) -> str:
        if ratio >= 0.8:
            return "High"
        if ratio >= 0.5:
            return "Medium"
        return "Low"
