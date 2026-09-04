"""
test_phenotype.py — тесты Genome Schema и Phenotype (AGENOMICS SPECIFICATION v1.0).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.5.0
"""

from agenomics import AgentGenome, ImpactTier
from agenomics.phenotype import compute_phenotype, describe_genome_schema, GENOME_SCHEMA


def test_same_genome_different_tier_gives_different_phenotype():
    """Ключевое свойство спецификации: одинаковый Genome в разном
    контексте (Tier) должен давать разный Phenotype."""
    kwargs = dict(id="x", transparency=80, bias_control=80, data_safety=80, drift_rate=0.15, has_ledger=False)
    genome_t1 = AgentGenome(**kwargs, tier_override=ImpactTier.TIER_1)
    genome_t3 = AgentGenome(**kwargs, tier_override=ImpactTier.TIER_3)

    pheno1 = compute_phenotype(genome_t1)
    pheno3 = compute_phenotype(genome_t3)

    assert pheno1.expressed_traits != pheno3.expressed_traits
    # TIER_3 должен штрафовать сильнее (ниже итоговые значения этих осей)
    assert pheno3.expressed_traits["accountability"] < pheno1.expressed_traits["accountability"]
    assert pheno3.expressed_traits["predictability"] < pheno1.expressed_traits["predictability"]
    # Оси без tier-penalty логики должны совпадать
    assert pheno1.expressed_traits["transparency"] == pheno3.expressed_traits["transparency"]


def test_same_genome_same_tier_gives_same_phenotype():
    """Обратная проверка: одинаковый контекст -> одинаковый Phenotype
    (детерминированность, не должно быть скрытой случайности)."""
    kwargs = dict(id="x", transparency=80, bias_control=80, data_safety=80, drift_rate=0.15, has_ledger=False, domain="finance")
    g1 = AgentGenome(**kwargs)
    g2 = AgentGenome(**kwargs)
    assert compute_phenotype(g1).expressed_traits == compute_phenotype(g2).expressed_traits


def test_phenotype_flags_insufficient_data():
    genome = AgentGenome(id="incomplete", domain="content")  # почти всё None
    pheno = compute_phenotype(genome)
    assert "transparency" in pheno.insufficient_axes
    assert "bias_control" in pheno.insufficient_axes


def test_genome_schema_covers_all_dataclass_fields():
    """Genome Schema не должна расходиться с реальными полями AgentGenome —
    иначе документация врёт о том, что реально принимает конструктор."""
    import dataclasses
    from agenomics import AgentGenome as AG

    dataclass_fields = {f.name for f in dataclasses.fields(AG)}
    schema_fields = {f.name for f in GENOME_SCHEMA}
    assert dataclass_fields == schema_fields, (
        f"Расхождение: в dataclass есть {dataclass_fields - schema_fields}, "
        f"в схеме есть {schema_fields - dataclass_fields}"
    )


def test_describe_genome_schema_returns_dicts():
    schema = describe_genome_schema()
    assert len(schema) == len(GENOME_SCHEMA)
    assert all(isinstance(f, dict) for f in schema)
    assert schema[0]["name"] == "id"
    assert schema[0]["required"] is True
