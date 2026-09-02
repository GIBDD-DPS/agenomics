"""
test_compatibility.py — тесты CompatibilityScorer методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.2.0
"""

from agenomics import AgentGenome, CompatibilityScorer


def test_compatible_pair_similar_agents():
    """Два похожих по этике/риску/стилю агента — высокая совместимость."""
    a = AgentGenome(id="support-a", bias_control=85, risk_tolerance=30, social_style=70, has_ledger=True)
    b = AgentGenome(id="support-b", bias_control=88, risk_tolerance=35, social_style=65, has_ledger=True)
    result = CompatibilityScorer().score_pair(a, b)
    assert result.score >= 85
    assert result.capped_reason is None


def test_ethics_conflict_triggers_cap():
    """Сильное этическое расхождение — жёсткий потолок 50, даже если
    остальные оси совпадают идеально."""
    a = AgentGenome(id="strict-agent", bias_control=95, risk_tolerance=20, social_style=50, has_ledger=True)
    b = AgentGenome(id="loose-agent", bias_control=40, risk_tolerance=20, social_style=50, has_ledger=True)
    result = CompatibilityScorer().score_pair(a, b)
    assert result.capped_reason is not None
    assert result.score <= 50


def test_social_style_mismatch_from_article_case():
    """Воспроизводит Кейс 2 из статьи: агент рекомендаций ('продающий',
    social_style низкий) vs агент поддержки ('эмпатичный', высокий)."""
    sales_agent = AgentGenome(
        id="recommendation-agent", bias_control=80, risk_tolerance=50,
        social_style=15, has_ledger=False,  # низкий accountability тоже добавляет трение
    )
    support_agent = AgentGenome(
        id="support-agent", bias_control=82, risk_tolerance=50,
        social_style=90, has_ledger=True,
    )
    result = CompatibilityScorer().score_pair(sales_agent, support_agent)
    # Большой разрыв social_style (75 пунктов) должен заметно снизить эту
    # конкретную ось, но не обрушить итоговый score — этика (вес 0.35)
    # у обоих агентов согласована, так что это "трение", а не критический
    # конфликт. Итог должен попасть в диапазон "заметная проблема, но не
    # критика" (аналог Conditional в Trust Score).
    assert result.breakdown["social_style"] <= 30
    assert 60 <= result.score < 85


def test_team_identifies_weakest_pair():
    """Команда из 3 агентов — должен корректно определяться самый
    несовместимый (узкое место) pair."""
    good_a = AgentGenome(id="a", bias_control=85, risk_tolerance=40, social_style=60, has_ledger=True)
    good_b = AgentGenome(id="b", bias_control=87, risk_tolerance=42, social_style=58, has_ledger=True)
    bad_c = AgentGenome(id="c", bias_control=30, risk_tolerance=95, social_style=5, has_ledger=False)

    result = CompatibilityScorer().score_team([good_a, good_b, bad_c])
    assert len(result.pairs) == 3  # C(3,2) = 3 пары
    assert result.weakest_pair is not None
    assert bad_c.id in (result.weakest_pair.agent_a, result.weakest_pair.agent_b)


def test_insufficient_data_not_overscored():
    """Отсутствие risk_tolerance/social_style не должно завышать оценку."""
    a = AgentGenome(id="minimal-a", bias_control=80)
    b = AgentGenome(id="minimal-b", bias_control=80)
    result = CompatibilityScorer().score_pair(a, b)
    assert set(result.insufficient_axes) >= {"risk_tolerance", "social_style"}
