"""
test_compat_ground_truth_v2.py — тесты расширенного Compatibility ground truth (v0.6.0).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.6.0
"""

from agenomics import CompatibilityScorer
from benchmark.scenarios import generate_compatibility_ground_truth
from benchmark.metrics import measure_compatibility_accuracy_v2


def test_generates_expected_count():
    cases = generate_compatibility_ground_truth(cases_per_category=30)
    assert len(cases) == 270  # 9 категорий x 30


def test_covers_all_nine_categories():
    cases = generate_compatibility_ground_truth(cases_per_category=10)
    categories = {c.category for c in cases}
    assert len(categories) == 9
    assert "role_complementarity" in categories
    assert "ethical_conflict" in categories


def test_ethical_conflict_always_hits_cap():
    """Категория ethical_conflict сконструирована так, что bias_gap > 40 —
    должна ВСЕГДА получать потолок Compatibility Score = 50."""
    cases = generate_compatibility_ground_truth(cases_per_category=20)
    scorer = CompatibilityScorer()
    ethical_cases = [c for c in cases if c.category == "ethical_conflict"]
    for case in ethical_cases:
        result = scorer.score_pair(case.genome_a, case.genome_b)
        assert result.score == 50.0
        assert result.capped_reason is not None


def test_role_complementarity_stays_compatible_despite_large_gap():
    """Большой risk_tolerance gap (~70) с ролями executor/reviewer НЕ
    должен штрафоваться — проверка, что role-aware логика реально
    работает на масштабе, а не только на одном примере в README."""
    cases = generate_compatibility_ground_truth(cases_per_category=15)
    scorer = CompatibilityScorer()
    role_cases = [c for c in cases if c.category == "role_complementarity"]
    assert len(role_cases) == 15
    for case in role_cases:
        result = scorer.score_pair(case.genome_a, case.genome_b)
        assert result.complementary_roles is True
        assert result.score >= 90  # несмотря на большой сырой gap


def test_compatible_and_conflicting_fully_separated_at_scale():
    """Ключевая проверка: разделение классов, найденное на 4 случаях в
    v0.1, должно ПОДТВЕРДИТЬСЯ на 270 случаях — не быть артефактом
    маленькой выборки."""
    result = measure_compatibility_accuracy_v2(cases_per_category=30)
    assert result.status == "computed"
    assert result.raw_data["fully_separated"] is True
    assert result.value == 1.0


def test_ambiguous_categories_excluded_from_binary_metric():
    """near_threshold и neutral не должны участвовать в бинарной accuracy —
    иначе метрика была бы искусственно занижена/завышена некорректной
    постановкой (пограничные случаи по определению не бинарны)."""
    result = measure_compatibility_accuracy_v2(cases_per_category=10)
    summary = result.raw_data["category_summary"]
    assert "near_threshold" in summary  # присутствуют в отчёте...
    assert "neutral" in summary
    # ...но не влияют на "fully_separated"/accuracy напрямую (это
    # проверяется косвенно через то, что accuracy = 1.0 несмотря на
    # широкий разброс near_threshold, видимый в summary)
    assert summary["near_threshold"]["min"] < summary["near_threshold"]["max"]
