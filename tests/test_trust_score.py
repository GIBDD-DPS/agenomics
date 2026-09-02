"""
test_trust_score.py — тесты TrustScorer методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.1
"""

from agenomics import AgentGenome, TrustScorer, Autonomy, ImpactTier


def test_support_agent_medium_quality():
    """Тест-кейс А: чат-бот поддержки, среднее качество, без логов."""
    genome = AgentGenome(
        id="support-bot",
        domain="support",
        autonomy=Autonomy.ADVISORY,
        transparency=60,
        bias_control=65,
        data_safety=55,
        drift_rate=0.15,
        has_ledger=False,
    )
    result = TrustScorer().score(genome)
    assert genome.tier == ImpactTier.TIER_2
    assert result.capped_reason is None  # Advisory — потолок не применяется
    assert 40 <= result.score <= 70


def test_finance_autonomous_agent_is_capped():
    """Тест-кейс Б: автономный финансовый агент без логов — должен
    получить жёсткий потолок Trust Score, даже с приличными осями."""
    genome = AgentGenome(
        id="cashflow-predictor",
        domain="finance",
        autonomy=Autonomy.AUTONOMOUS,
        transparency=75,
        bias_control=80,
        data_safety=85,
        drift_rate=0.1,
        has_ledger=False,  # accountability = 30, ниже порога 80
    )
    result = TrustScorer().score(genome)
    assert genome.tier == ImpactTier.TIER_3
    assert result.capped_reason is not None
    assert result.score <= 70
    assert result.label in ("Conditional", "High Risk")


def test_insufficient_information_not_overscored():
    """Отсутствие данных не должно приводить к завышенной оценке."""
    genome = AgentGenome(id="unknown-agent", domain=None)
    result = TrustScorer().score(genome)
    assert set(result.insufficient_axes) == {
        "transparency", "bias_control", "data_safety", "predictability",
    }
    assert result.score <= 55


def test_trusted_agent_with_ledger_and_advisory():
    genome = AgentGenome(
        id="content-writer",
        domain="content",  # TIER_1
        autonomy=Autonomy.ADVISORY,
        transparency=90,
        bias_control=88,
        data_safety=92,
        drift_rate=0.03,
        has_ledger=True,
    )
    result = TrustScorer().score(genome)
    assert result.label == "Trusted"
    assert result.capped_reason is None


def test_how_to_guide_matches_weak_axes():
    """how_to должен содержать практическую подсказку ровно для тех осей,
    что попали в recommendations — не больше и не меньше."""
    genome = AgentGenome(
        id="needs-help", domain="support", autonomy=Autonomy.AUTONOMOUS,
        transparency=85, bias_control=72, data_safety=90,
        drift_rate=0.35, has_ledger=False,
    )
    result = TrustScorer().score(genome)
    assert "accountability" in result.how_to
    assert len(result.how_to["accountability"]) > 20  # содержательный текст, не заглушка
    # Сильные оси (>= 80) не должны попадать в how_to
    assert "data_safety" not in result.how_to


def test_how_to_empty_for_fully_trusted_agent():
    genome = AgentGenome(
        id="excellent", domain="content", autonomy=Autonomy.ADVISORY,
        transparency=95, bias_control=95, data_safety=95, drift_rate=0.02, has_ledger=True,
    )
    result = TrustScorer().score(genome)
    assert result.how_to == {}
