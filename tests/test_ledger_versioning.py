"""
test_ledger_versioning.py. Тесты Genome Versioning в GenomeLedger (v0.8.0).

Проект: Prizolov Lab
"""

from agenomics import AgentGenome, GenomeLedger, TrustScorer


def _record(ledger, genome, **kwargs):
    return ledger.record(genome, TrustScorer().score(genome), **kwargs)


def test_first_version_has_no_parent():
    ledger = GenomeLedger()
    entry = _record(ledger, AgentGenome(id="a", bias_control=80), created_by="dima", change_reason="initial")
    assert entry.parent_genome_hash is None
    assert entry.genome_version == 1
    assert entry.created_by == "dima"
    assert entry.change_reason == "initial"


def test_changed_genome_links_to_previous_version():
    ledger = GenomeLedger()
    v1 = _record(ledger, AgentGenome(id="a", bias_control=80))
    v2 = _record(ledger, AgentGenome(id="a", bias_control=90), change_reason="added bias guardrails")
    assert v2.parent_genome_hash == v1.genome_hash
    assert v2.genome_version == 2


def test_reaudit_of_same_genome_is_not_a_new_version():
    ledger = GenomeLedger()
    genome = AgentGenome(id="a", bias_control=80)
    _record(ledger, genome)
    v2 = _record(ledger, AgentGenome(id="a", bias_control=90))
    reaudit = _record(ledger, AgentGenome(id="a", bias_control=90))
    assert reaudit.genome_version == v2.genome_version == 2
    assert reaudit.parent_genome_hash == v2.parent_genome_hash


def test_versions_are_tracked_per_agent():
    ledger = GenomeLedger()
    _record(ledger, AgentGenome(id="a", bias_control=80))
    b1 = _record(ledger, AgentGenome(id="b", bias_control=50))
    assert b1.genome_version == 1
    assert b1.parent_genome_hash is None


def test_explicit_parent_overrides_auto():
    ledger = GenomeLedger()
    source = _record(ledger, AgentGenome(id="template", bias_control=85))
    fork = _record(ledger, AgentGenome(id="fork", bias_control=86), parent_genome_hash=source.genome_hash)
    assert fork.parent_genome_hash == source.genome_hash

    _record(ledger, AgentGenome(id="c", bias_control=10))
    rewritten = _record(ledger, AgentGenome(id="c", bias_control=70), parent_genome_hash=None)
    assert rewritten.parent_genome_hash is None  # явный None: создан с нуля
    assert rewritten.genome_version == 2


def test_lineage_lists_distinct_versions_in_order():
    ledger = GenomeLedger()
    v1 = _record(ledger, AgentGenome(id="a", bias_control=80))
    _record(ledger, AgentGenome(id="a", bias_control=80))  # повторный аудит v1
    v2 = _record(ledger, AgentGenome(id="a", bias_control=90))
    lineage = ledger.lineage("a")
    assert [e.genome_version for e in lineage] == [1, 2]
    assert [e.genome_hash for e in lineage] == [v1.genome_hash, v2.genome_hash]
    assert len(ledger.entries_for("a")) == 3


def test_tampering_with_versioning_fields_is_detected():
    ledger = GenomeLedger()
    _record(ledger, AgentGenome(id="a", bias_control=80))
    _record(ledger, AgentGenome(id="a", bias_control=90), change_reason="real reason")
    assert ledger.verify_integrity() is True
    ledger._entries[1].change_reason = "rewritten after the fact"
    assert ledger.verify_integrity() is False


def test_export_includes_versioning_fields():
    import json
    ledger = GenomeLedger()
    _record(ledger, AgentGenome(id="a", bias_control=80), created_by="pipeline")
    exported = json.loads(ledger.export_json())[0]
    assert exported["created_by"] == "pipeline"
    assert exported["genome_version"] == 1
    assert "parent_genome_hash" in exported
