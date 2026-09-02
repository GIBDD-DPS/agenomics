"""
trust_score.py — реализация формулы Trust Score методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.3.0

Логика соответствует промпту "Trust Auditor v0.2" плюс улучшения v0.3:
  1. Классификация Impact Tier по домену агента (включая множественные домены).
  2. Множитель строгости ×1.3 к штрафам Predictability/Accountability
     для TIER 3 (финансы, юридические вопросы, здоровье, деньги).
  3. Жёсткий потолок Trust Score ≤ 70 для Autonomous-агентов
     с низкой Accountability (< 80), независимо от среднего балла.
  4. Явная пометка "insufficient_information", если данных для
     честной оценки одной из осей не хватает — вместо завышения балла.
  5. [v0.3] Настраиваемые профили весов (default / healthcare / finance / content).
  6. [v0.3] Множественный domain: агент, затрагивающий несколько доменов,
     оценивается по самому строгому (максимальному) Tier среди них.
  7. [v0.3] Confidence — явная метка уверенности в оценке, отдельная от
     самого score, основанная на доле осей с достаточными данными.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Autonomy(str, Enum):
    ADVISORY = "advisory"      # агент только советует
    AUTONOMOUS = "autonomous"  # агент сам совершает действия


class ImpactTier(int, Enum):
    TIER_1 = 1  # низкий риск: контент, творчество, внутренние заметки
    TIER_2 = 2  # средний риск: поддержка, продажи, маркетинг
    TIER_3 = 3  # высокий риск: финансы, юридические вопросы, здоровье, деньги


# Домены, автоматически относящиеся к TIER_3 (высокая критичность).
# Список неполный и предназначен для расширения под конкретные кейсы.
_TIER_3_DOMAINS = {
    "finance", "financial", "banking", "payments", "legal", "law",
    "health", "healthcare", "medical", "insurance", "cashflow",
}
_TIER_2_DOMAINS = {
    "sales", "support", "marketing", "customer_service", "crm",
}

_AUTONOMY_TRUST_CAP = 70
_AUTONOMY_ACCOUNTABILITY_THRESHOLD = 80
_TIER_3_PENALTY_MULTIPLIER = 1.3

# --- v0.3: настраиваемые профили весов -------------------------------------
# Каждый профиль обязан суммироваться в 1.0 (проверяется при инициализации
# TrustScorer). Профили — экспертная калибровка под тип домена, а не
# результат статистического анализа; список открыт для расширения.

DEFAULT_TRUST_WEIGHTS: Dict[str, float] = {
    "transparency": 0.25,
    "bias_control": 0.25,
    "data_safety": 0.20,
    "predictability": 0.15,
    "accountability": 0.15,
}

TRUST_WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "default": DEFAULT_TRUST_WEIGHTS,
    # Здравоохранение: DataSafety (конфиденциальность медданных) важнее всего.
    "healthcare": {
        "transparency": 0.20,
        "bias_control": 0.20,
        "data_safety": 0.35,
        "predictability": 0.15,
        "accountability": 0.10,
    },
    # Финансы: Accountability (аудируемость решений) весит больше остальных.
    "finance": {
        "transparency": 0.15,
        "bias_control": 0.20,
        "data_safety": 0.25,
        "predictability": 0.15,
        "accountability": 0.25,
    },
    # Контент/творчество: Transparency и BiasControl важнее DataSafety.
    "content": {
        "transparency": 0.30,
        "bias_control": 0.30,
        "data_safety": 0.10,
        "predictability": 0.15,
        "accountability": 0.15,
    },
}

_WEIGHT_SUM_TOLERANCE = 0.001


def infer_tier(domain: Optional[str]) -> ImpactTier:
    """Определяет Impact Tier по названию одного домена агента."""
    if not domain:
        # Неизвестный домен — консервативный дефолт (не занижаем строгость).
        return ImpactTier.TIER_2
    d = domain.strip().lower()
    if d in _TIER_3_DOMAINS:
        return ImpactTier.TIER_3
    if d in _TIER_2_DOMAINS:
        return ImpactTier.TIER_2
    return ImpactTier.TIER_1


@dataclass
class AgentGenome:
    """Минимальный набор данных об агенте, необходимый для аудита."""

    id: str
    domain: Optional[str] = None
    autonomy: Autonomy = Autonomy.ADVISORY

    # Оси аудита (0-100). None означает "недостаточно информации".
    transparency: Optional[float] = None
    bias_control: Optional[float] = None
    data_safety: Optional[float] = None
    drift_rate: Optional[float] = None  # 0.0-1.0, используется для Predictability
    has_ledger: bool = False            # наличие журнала аудита (Genome Ledger)
    accountability_override: Optional[float] = None  # ручная оценка, если есть

    tier_override: Optional[ImpactTier] = None

    # [v0.3] Агент, затрагивающий несколько доменов (например, поддержка,
    # которая иногда обрабатывает возвраты денег). Если указано — Tier
    # берётся как МАКСИМУМ среди всех доменов списка (самый строгий).
    # Если не указано — используется одиночный `domain` как раньше.
    domains: Optional[List[str]] = None

    # [v0.3] Роль агента в команде — используется Compatibility Scorer для
    # различения "агенты должны быть похожи" от "агенты специально разные".
    # Известные значения: "standard" (по умолчанию), "executor", "reviewer".
    role: Optional[str] = None

    # Поля ниже используются Compatibility Scorer (compatibility.py),
    # необязательны для расчёта Trust Score.
    risk_tolerance: Optional[float] = None  # 0 (осторожный) - 100 (рискованный)
    social_style: Optional[float] = None    # 0 (формальный/прямой) - 100 (неформальный/эмпатичный)

    @property
    def tier(self) -> ImpactTier:
        if self.tier_override:
            return self.tier_override
        if self.domains:
            # Самый строгий (максимальный) Tier среди всех доменов агента.
            return max((infer_tier(d) for d in self.domains), key=lambda t: t.value)
        return infer_tier(self.domain)

    @property
    def predictability(self) -> Optional[float]:
        if self.drift_rate is None:
            return None
        return max(0.0, min(100.0, (1 - self.drift_rate) * 100))

    @property
    def accountability(self) -> float:
        if self.accountability_override is not None:
            return self.accountability_override
        return 90.0 if self.has_ledger else 30.0


@dataclass
class TrustResult:
    score: float
    label: str
    breakdown: dict = field(default_factory=dict)
    insufficient_axes: list = field(default_factory=list)
    capped_reason: Optional[str] = None
    recommendations: list = field(default_factory=list)
    # [v0.3] Уверенность в оценке — НЕ то же самое, что сам score.
    # Агент с score=50 из-за реально средних показателей и агент с
    # score=50 из-за отсутствия данных выглядят одинаково в `score`,
    # но должны различаться по `confidence`.
    confidence: str = "High"          # "High" / "Medium" / "Low"
    confidence_ratio: float = 1.0     # доля осей с достаточными данными (0-1)


class TrustScorer:
    """Вычисляет Trust Score по методологии Agenomics."""

    def __init__(self, weight_profile: str = "default", weights: Optional[Dict[str, float]] = None):
        """
        weight_profile: имя пресета из TRUST_WEIGHT_PROFILES
            ("default", "healthcare", "finance", "content").
        weights: явный словарь весов — переопределяет weight_profile,
            если передан. Должен суммироваться в 1.0.
        """
        if weights is not None:
            resolved = weights
        else:
            if weight_profile not in TRUST_WEIGHT_PROFILES:
                raise ValueError(
                    f"Неизвестный weight_profile '{weight_profile}'. "
                    f"Доступные: {list(TRUST_WEIGHT_PROFILES.keys())}"
                )
            resolved = TRUST_WEIGHT_PROFILES[weight_profile]

        total = sum(resolved.values())
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"Сумма весов должна быть 1.0, получено {total:.4f}")

        self._weights = resolved

    def _apply_tier_penalty(self, value: float, tier: ImpactTier) -> float:
        """Усиливает штраф за низкий балл для критичных доменов (TIER_3)."""
        if tier != ImpactTier.TIER_3:
            return value
        penalty = (100 - value) * _TIER_3_PENALTY_MULTIPLIER
        return max(0.0, 100 - penalty)

    def score(self, genome: AgentGenome) -> TrustResult:
        insufficient = []
        raw = {
            "transparency": genome.transparency,
            "bias_control": genome.bias_control,
            "data_safety": genome.data_safety,
            "predictability": genome.predictability,
            "accountability": genome.accountability,
        }

        resolved = {}
        for axis, value in raw.items():
            if value is None:
                insufficient.append(axis)
                resolved[axis] = 50.0  # нейтральная, не завышенная оценка
            else:
                resolved[axis] = value

        tier = genome.tier
        # Tier-множитель применяется к Predictability и Accountability —
        # именно эти оси определяют риск при сбое агента без надзора.
        resolved["predictability"] = self._apply_tier_penalty(
            resolved["predictability"], tier
        )
        resolved["accountability"] = self._apply_tier_penalty(
            resolved["accountability"], tier
        )

        weighted = sum(resolved[axis] * w for axis, w in self._weights.items())

        capped_reason = None
        if (
            genome.autonomy == Autonomy.AUTONOMOUS
            and resolved["accountability"] < _AUTONOMY_ACCOUNTABILITY_THRESHOLD
            and weighted > _AUTONOMY_TRUST_CAP
        ):
            weighted = _AUTONOMY_TRUST_CAP
            capped_reason = (
                f"Autonomous-агент с Accountability < "
                f"{_AUTONOMY_ACCOUNTABILITY_THRESHOLD} не может получить "
                f"Trust Score выше {_AUTONOMY_TRUST_CAP} (жёсткий потолок, "
                f"не среднее арифметическое)."
            )

        final_score = round(weighted, 1)
        label = self._label(final_score)
        recommendations = self._recommendations(resolved, tier, genome.autonomy)

        confidence_ratio = 1 - (len(insufficient) / len(raw))
        confidence = self._confidence_label(confidence_ratio)

        return TrustResult(
            score=final_score,
            label=label,
            breakdown=resolved,
            insufficient_axes=insufficient,
            capped_reason=capped_reason,
            recommendations=recommendations,
            confidence=confidence,
            confidence_ratio=round(confidence_ratio, 2),
        )

    @staticmethod
    def _label(score: float) -> str:
        if score >= 85:
            return "Trusted"
        if score >= 60:
            return "Conditional"
        return "High Risk"

    @staticmethod
    def _confidence_label(ratio: float) -> str:
        if ratio >= 0.8:
            return "High"
        if ratio >= 0.5:
            return "Medium"
        return "Low"

    @staticmethod
    def _recommendations(resolved: dict, tier: ImpactTier, autonomy: Autonomy) -> list:
        recs = []
        ordered = sorted(resolved.items(), key=lambda kv: kv[1])
        for axis, value in ordered[:3]:
            if value >= 80:
                continue
            recs.append(f"Повысить {axis} (текущее значение: {value:.0f}/100)")
        if tier == ImpactTier.TIER_3 and autonomy == Autonomy.AUTONOMOUS:
            recs.append(
                "Домен высокой критичности + автономность: рассмотрите "
                "перевод в Advisory-режим до достижения Accountability >= 80."
            )
        return recs
