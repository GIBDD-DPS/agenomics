"""
trust_score.py — реализация формулы Trust Score методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.3

Логика соответствует промпту "Trust Auditor v0.2" плюс улучшения v0.3-0.4:
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
  8. [v0.4.1] how_to — практическая подсказка "как сделать" для каждой
     оси, попавшей в рекомендации (используется в reports.py).
  9. [v0.4.3] language — параметр TrustScorer(language="ru"|"en").
     Определяет язык текста recommendations, capped_reason и how_to.
     Поддерживаются "ru" (по умолчанию) и "en"; список расширяем —
     см. HOW_TO_GUIDE_TRANSLATIONS и *_TEMPLATES ниже.
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

# Практические подсказки "как это сделать" для каждой оси — используются
# в рекомендациях TrustResult.how_to и в отчётах (reports.py). Это тоже
# экспертная эвристика: общие практики, а не гарантированный рецепт для
# конкретного агента — реальная реализация зависит от вашего стека.
HOW_TO_GUIDE: Dict[str, str] = {
    "transparency": (
        "Добавьте в ответ агента краткое обоснование решения (reasoning) — "
        "пользователь должен понимать, почему дан именно такой ответ, "
        "а не просто получать результат."
    ),
    "bias_control": (
        "Добавьте в системный промпт явные ограничения против дискриминации "
        "и манипуляции, с 1-2 few-shot примерами корректного этичного отказа "
        "в спорной ситуации."
    ),
    "data_safety": (
        "Ограничьте доступ агента к персональным/платёжным данным по "
        "принципу минимально необходимого; добавьте явный запрет на "
        "передачу данных куда-либо за пределы разрешённого потока."
    ),
    "predictability": (
        "Пропишите в промпте явные правила для edge-cases (противоречивые "
        "данные, нестандартные запросы) — это снижает дрейф поведения "
        "(drift_rate) сильнее, чем общие инструкции."
    ),
    "accountability": (
        "Включите ведение журнала решений агента (has_ledger=True в "
        "AgentGenome) — неизменяемая история action/decision поднимает "
        "эту ось быстрее всего и снимает потолок автономности."
    ),
}

# [v0.4.3] Английский перевод HOW_TO_GUIDE. HOW_TO_GUIDE (выше) сохранён
# как есть для обратной совместимости (semver 0.x, но лишний breaking
# change без нужды — плохая практика) — это дефолт для language="ru".
_HOW_TO_GUIDE_EN: Dict[str, str] = {
    "transparency": (
        "Add a brief reasoning explanation to the agent's response — the "
        "user should understand why a particular answer was given, not "
        "just receive the result."
    ),
    "bias_control": (
        "Add explicit anti-discrimination and anti-manipulation constraints "
        "to the system prompt, with 1-2 few-shot examples of a correct, "
        "ethical refusal in a borderline situation."
    ),
    "data_safety": (
        "Restrict the agent's access to personal/payment data on a "
        "need-to-know basis; add an explicit prohibition on sharing data "
        "outside the permitted flow."
    ),
    "predictability": (
        "Add explicit rules for edge cases (conflicting data, non-standard "
        "requests) to the prompt — this reduces behavioral drift "
        "(drift_rate) more effectively than general instructions."
    ),
    "accountability": (
        "Enable a decision log for the agent (has_ledger=True in "
        "AgentGenome) — an immutable action/decision history raises this "
        "axis the fastest and lifts the autonomy ceiling."
    ),
}

HOW_TO_GUIDE_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": HOW_TO_GUIDE,
    "en": _HOW_TO_GUIDE_EN,
}

# [v0.4.3] Шаблоны текстов рекомендаций/потолка по языкам.
_RECOMMENDATION_TEMPLATE = {
    "ru": "Повысить {axis} (текущее значение: {value:.0f}/100)",
    "en": "Improve {axis} (current value: {value:.0f}/100)",
}
_TIER3_AUTONOMY_RECOMMENDATION = {
    "ru": (
        "Домен высокой критичности + автономность: рассмотрите "
        "перевод в Advisory-режим до достижения Accountability >= 80."
    ),
    "en": (
        "High-criticality domain + autonomy: consider switching to "
        "Advisory mode until Accountability reaches >= 80."
    ),
}
_CAPPED_REASON_TEMPLATE = {
    "ru": (
        "Autonomous-агент с Accountability < {threshold} не может получить "
        "Trust Score выше {cap} (жёсткий потолок, не среднее арифметическое)."
    ),
    "en": (
        "An Autonomous agent with Accountability < {threshold} cannot "
        "receive a Trust Score above {cap} (a hard ceiling, not an average)."
    ),
}
SUPPORTED_LANGUAGES = tuple(HOW_TO_GUIDE_TRANSLATIONS.keys())

# Атрибуция, включаемая в каждый результат — промпт, код, API.
# Цель: любой скопированный/расшаренный отчёт несёт ссылку на источник.
AGENOMICS_ATTRIBUTION = "Powered by Agenomics (Trust Score methodology) — prizolov.ru · by Dm.Andreyanov, Prizolov Lab"


def _validate_range(name: str, value: Optional[float], lo: float = 0.0, hi: float = 100.0) -> None:
    """Проверяет, что значение оси попадает в допустимый диапазон.
    None пропускается — это законное состояние "нет данных"."""
    if value is not None and not (lo <= value <= hi):
        raise ValueError(f"{name} должен быть в диапазоне [{lo}, {hi}], получено {value}")


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

    def __post_init__(self):
        """Валидация диапазонов — библиотека не должна молча принимать
        мусорные значения (bias_control=150, drift_rate=-0.3 и т.п.),
        даже при прямом использовании в обход API/Pydantic."""
        for axis_name in ("transparency", "bias_control", "data_safety", "risk_tolerance", "social_style"):
            _validate_range(axis_name, getattr(self, axis_name))
        _validate_range("accountability_override", self.accountability_override)
        if self.drift_rate is not None and not (0.0 <= self.drift_rate <= 1.0):
            raise ValueError(f"drift_rate должен быть в диапазоне [0.0, 1.0], получено {self.drift_rate}")

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
    attribution: str = AGENOMICS_ATTRIBUTION
    how_to: dict = field(default_factory=dict)  # axis -> практическая подсказка "как сделать"


class TrustScorer:
    """Вычисляет Trust Score по методологии Agenomics."""

    def __init__(
        self,
        weight_profile: str = "default",
        weights: Optional[Dict[str, float]] = None,
        language: str = "ru",
    ):
        """
        weight_profile: имя пресета из TRUST_WEIGHT_PROFILES
            ("default", "healthcare", "finance", "content").
        weights: явный словарь весов — переопределяет weight_profile,
            если передан. Должен суммироваться в 1.0.
        language: язык текстов recommendations/capped_reason/how_to —
            "ru" (по умолчанию) или "en". Список поддерживаемых языков:
            SUPPORTED_LANGUAGES.
        """
        if language not in HOW_TO_GUIDE_TRANSLATIONS:
            raise ValueError(
                f"Неизвестный language '{language}'. "
                f"Доступные: {list(HOW_TO_GUIDE_TRANSLATIONS.keys())}"
            )
        self._language = language

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
            capped_reason = _CAPPED_REASON_TEMPLATE[self._language].format(
                threshold=_AUTONOMY_ACCOUNTABILITY_THRESHOLD,
                cap=_AUTONOMY_TRUST_CAP,
            )

        final_score = round(weighted, 1)
        label = self._label(final_score)
        recommendations, weak_axes = self._recommendations(
            resolved, tier, genome.autonomy, self._language
        )
        how_to_source = HOW_TO_GUIDE_TRANSLATIONS[self._language]
        how_to = {axis: how_to_source[axis] for axis in weak_axes if axis in how_to_source}

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
            how_to=how_to,
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
    def _recommendations(resolved: dict, tier: ImpactTier, autonomy: Autonomy, language: str = "ru"):
        recs = []
        weak_axes = []
        ordered = sorted(resolved.items(), key=lambda kv: kv[1])
        for axis, value in ordered[:3]:
            if value >= 80:
                continue
            recs.append(_RECOMMENDATION_TEMPLATE[language].format(axis=axis, value=value))
            weak_axes.append(axis)
        if tier == ImpactTier.TIER_3 and autonomy == Autonomy.AUTONOMOUS:
            recs.append(_TIER3_AUTONOMY_RECOMMENDATION[language])
        return recs, weak_axes
