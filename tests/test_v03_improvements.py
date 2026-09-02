"""
test_v03_improvements.py — тесты 4 улучшений методологии v0.3:
настраиваемые веса, роли в Compatibility, множественный domain, confidence.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.3.0
"""

from agenomics import (
    AgentGenome, TrustScorer, CompatibilityScorer, ImpactTier,
    TRUST_WEIGHT_PROFILES, COMPAT_WEIGHT_PROFILES,
)


def _assert_raises(exc_type, fn):
    """Мини-замена pytest.raises, чтобы не тянуть pytest как зависимость."""
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"Ожидалось исключение {exc_type.__name__}, но оно не было вызвано")


# --- 1. Настраиваемые веса ---------------------------------------------

def test_all_trust_weight_profiles_sum_to_one():
    for name, weights in TRUST_WEIGHT_PROFILES.items():
        assert abs(sum(weights.values()) - 1.0) < 0.001, f"Профиль '{name}' не суммируется в 1.0"


def test_all_compat_weight_profiles_sum_to_one():
    for name, weights in COMPAT_WEIGHT_PROFILES.items():
        assert abs(sum(weights.values()) - 1.0) < 0.001, f"Профиль '{name}' не суммируется в 1.0"


def test_healthcare_profile_penalizes_data_safety_more():
    """В healthcare-профиле низкий DataSafety должен просаживать итог
    сильнее, чем в default-профиле (при прочих равных)."""
    genome = AgentGenome(
        id="medical-agent", domain="healthcare", autonomy="advisory",
        transparency=90, bias_control=90, data_safety=30,  # низкий DataSafety
        drift_rate=0.05, has_ledger=True,
    )
    default_score = TrustScorer(weight_profile="default").score(genome).score
    healthcare_score = TrustScorer(weight_profile="healthcare").score(genome).score
    assert healthcare_score < default_score


def test_invalid_weights_raise_error():
    _assert_raises(ValueError, lambda: TrustScorer(weights={"transparency": 0.5, "bias_control": 0.6}))


def test_unknown_profile_name_raises_error():
    _assert_raises(ValueError, lambda: TrustScorer(weight_profile="nonexistent-profile"))


# --- 2. Роли агентов в Compatibility -------------------------------------

def test_executor_reviewer_risk_mismatch_not_penalized():
    """Осторожный reviewer + рискованный executor — не должно штрафоваться
    по оси risk_tolerance, в отличие от той же пары без ролей."""
    cautious_reviewer = AgentGenome(
        id="reviewer", role="reviewer", bias_control=85,
        risk_tolerance=10, social_style=50, has_ledger=True,
    )
    risky_executor = AgentGenome(
        id="executor", role="executor", bias_control=85,
        risk_tolerance=90, social_style=50, has_ledger=True,
    )
    result = CompatibilityScorer().score_pair(cautious_reviewer, risky_executor)
    assert result.complementary_roles is True
    assert result.breakdown["risk_tolerance"] == 100.0

    # Без ролей та же разница в risk_tolerance ДОЛЖНА штрафоваться.
    no_role_a = AgentGenome(id="a", bias_control=85, risk_tolerance=10, social_style=50, has_ledger=True)
    no_role_b = AgentGenome(id="b", bias_control=85, risk_tolerance=90, social_style=50, has_ledger=True)
    result_no_roles = CompatibilityScorer().score_pair(no_role_a, no_role_b)
    assert result_no_roles.complementary_roles is False
    assert result_no_roles.breakdown["risk_tolerance"] < 50


def test_non_complementary_roles_still_penalized():
    """Два 'standard' агента с разной risk_tolerance — обычный штраф,
    роль-специфичная логика не должна срабатывать зря."""
    a = AgentGenome(id="a", role="standard", bias_control=85, risk_tolerance=10, social_style=50, has_ledger=True)
    b = AgentGenome(id="b", role="standard", bias_control=85, risk_tolerance=90, social_style=50, has_ledger=True)
    result = CompatibilityScorer().score_pair(a, b)
    assert result.complementary_roles is False
    assert result.breakdown["risk_tolerance"] < 50


# --- 3. Множественный domain / гибкий Tier -------------------------------

def test_multi_domain_uses_strictest_tier():
    """Агент поддержки, который также обрабатывает возвраты денег
    (finance), должен классифицироваться по самому строгому Tier (3)."""
    genome = AgentGenome(id="support-refunds", domains=["support", "finance"])
    assert genome.tier == ImpactTier.TIER_3


def test_multi_domain_all_low_tier_stays_low():
    genome = AgentGenome(id="content-multi", domains=["content", "marketing"])
    assert genome.tier == ImpactTier.TIER_2  # marketing = TIER_2, содержание = TIER_1 -> max = TIER_2


def test_tier_override_still_wins_over_domains():
    genome = AgentGenome(id="forced", domains=["content"], tier_override=ImpactTier.TIER_3)
    assert genome.tier == ImpactTier.TIER_3


def test_single_domain_backward_compatible():
    """Старый способ (один domain, без domains) должен работать как раньше."""
    genome = AgentGenome(id="old-style", domain="finance")
    assert genome.tier == ImpactTier.TIER_3


# --- 4. Confidence ---------------------------------------------------------

def test_full_data_gives_high_confidence():
    genome = AgentGenome(
        id="complete", domain="content", transparency=80, bias_control=80,
        data_safety=80, drift_rate=0.1, has_ledger=True,
    )
    result = TrustScorer().score(genome)
    assert result.confidence == "High"
    assert result.confidence_ratio == 1.0


def test_missing_data_gives_low_confidence_not_just_average_score():
    """Агент почти без данных должен получить низкий confidence, даже
    если итоговый score из-за нейтральных заглушек выглядит 'средне'."""
    genome = AgentGenome(id="unknown", domain=None)  # почти всё None
    result = TrustScorer().score(genome)
    assert result.confidence in ("Low", "Medium")
    assert result.confidence_ratio < 1.0
    # Ключевая проверка: confidence отличает "мало данных" от "средний агент".
    fully_average_genome = AgentGenome(
        id="truly-average", domain="content", transparency=50, bias_control=50,
        data_safety=50, drift_rate=0.5, has_ledger=False,
    )
    average_result = TrustScorer().score(fully_average_genome)
    assert average_result.confidence == "High"  # данные есть, просто средние
    assert average_result.confidence_ratio > result.confidence_ratio


def test_compatibility_confidence_reflects_missing_data():
    a = AgentGenome(id="a", bias_control=80)  # risk_tolerance, social_style не заданы
    b = AgentGenome(id="b", bias_control=82)
    result = CompatibilityScorer().score_pair(a, b)
    assert result.confidence in ("Low", "Medium")
    assert result.confidence_ratio < 1.0
