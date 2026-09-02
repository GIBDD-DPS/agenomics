"""
test_v04_modules.py — тесты 7 новых модулей v0.4:
Drift Monitor, Incident Feedback, Genome Ledger, Genome Matchmaker,
Chain Risk Aggregator, Prompt-to-Genome Extractor, Reports.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.0
"""

from datetime import datetime, timedelta, timezone

from agenomics import (
    AgentGenome, TrustScorer, CompatibilityScorer,
    DriftMonitor, IncidentFeedback, Incident, IncidentSeverity,
    GenomeLedger, GenomeMatchmaker, ChainRiskAggregator,
    PromptToGenomeExtractor, ExtractionError,
    trust_report, compatibility_report,
)


def _assert_raises(exc_type, fn):
    try:
        fn()
    except exc_type:
        return
    raise AssertionError(f"Ожидалось исключение {exc_type.__name__}, но оно не было вызвано")


# --- 1. Drift Monitor ------------------------------------------------------

def test_drift_monitor_detects_degrading_trend():
    monitor = DriftMonitor()
    base = datetime.now(timezone.utc)
    for i, score in enumerate([90, 80, 70, 60]):
        monitor.record("agent-1", score, timestamp=base + timedelta(days=i))
    report = monitor.report("agent-1")
    assert report.trend == "degrading"
    assert report.alert is True
    assert report.slope < 0


def test_drift_monitor_stable_trend_no_alert():
    monitor = DriftMonitor()
    for score in [80, 81, 79, 80]:
        monitor.record("agent-2", score)
    report = monitor.report("agent-2")
    assert report.trend == "stable"
    assert report.alert is False


def test_drift_monitor_insufficient_data():
    monitor = DriftMonitor()
    monitor.record("agent-3", 80)
    report = monitor.report("agent-3")
    assert report.trend == "insufficient_data"
    assert report.alert is False


def test_drift_monitor_unknown_agent_raises():
    monitor = DriftMonitor()
    _assert_raises(ValueError, lambda: monitor.report("no-such-agent"))


# --- 2. Incident Feedback --------------------------------------------------

def test_incident_feedback_lowers_score():
    feedback = IncidentFeedback()
    incidents = [
        Incident("Слил email клиента в лог", IncidentSeverity.SEVERE, axis="data_safety"),
    ]
    result = feedback.apply(declared_score=90, declared_label="Trusted", incidents=incidents)
    assert result.observed_score < result.declared_score
    assert result.observed_score == 65.0  # 90 - 25 (severe penalty)


def test_incident_feedback_label_can_change():
    feedback = IncidentFeedback()
    incidents = [Incident("Утечка данных", IncidentSeverity.SEVERE)] * 3  # 3 severe = 75, но потолок 60
    result = feedback.apply(declared_score=90, declared_label="Trusted", incidents=incidents)
    assert result.total_penalty == 60.0  # применён _MAX_TOTAL_PENALTY
    assert result.observed_score == 30.0
    assert result.observed_label == "High Risk"
    assert result.label_changed is True


def test_incident_feedback_no_incidents_no_change():
    feedback = IncidentFeedback()
    result = feedback.apply(declared_score=90, declared_label="Trusted", incidents=[])
    assert result.observed_score == 90
    assert result.label_changed is False


# --- 3. Genome Ledger -------------------------------------------------------

def test_ledger_records_and_chains_hashes():
    ledger = GenomeLedger()
    genome1 = AgentGenome(id="agent-x", bias_control=80)
    result1 = TrustScorer().score(genome1)
    entry1 = ledger.record(genome1, result1)
    assert entry1.prev_hash is None  # первая запись

    genome2 = AgentGenome(id="agent-y", bias_control=82)
    result2 = TrustScorer().score(genome2)
    entry2 = ledger.record(genome2, result2)
    assert entry2.prev_hash == entry1.genome_hash  # цепочка

    assert ledger.verify_integrity() is True


def test_ledger_same_genome_produces_same_hash():
    genome_a = AgentGenome(id="same", bias_control=80, transparency=70)
    genome_b = AgentGenome(id="same", bias_control=80, transparency=70)
    ledger = GenomeLedger()
    entry_a = ledger.record(genome_a, TrustScorer().score(genome_a))
    entry_b = ledger.record(genome_b, TrustScorer().score(genome_b))
    assert entry_a.genome_hash == entry_b.genome_hash  # детерминированный хэш


def test_ledger_entries_for_filters_by_agent():
    ledger = GenomeLedger()
    g1 = AgentGenome(id="a", bias_control=80)
    g2 = AgentGenome(id="b", bias_control=80)
    ledger.record(g1, TrustScorer().score(g1))
    ledger.record(g2, TrustScorer().score(g2))
    ledger.record(g1, TrustScorer().score(g1))
    assert len(ledger.entries_for("a")) == 2
    assert len(ledger.entries_for("b")) == 1


# --- 4. Genome Matchmaker ----------------------------------------------------

def test_matchmaker_finds_best_pair():
    good_match_a = AgentGenome(id="a", bias_control=85, risk_tolerance=50, social_style=50, has_ledger=True)
    good_match_b = AgentGenome(id="b", bias_control=85, risk_tolerance=50, social_style=50, has_ledger=True)
    bad_match_c = AgentGenome(id="c", bias_control=20, risk_tolerance=95, social_style=5, has_ledger=False)

    matchmaker = GenomeMatchmaker()
    result = matchmaker.best_team([good_match_a, good_match_b, bad_match_c], roles=["executor", "reviewer"])
    assigned_ids = set(result.assignment.values())
    assert assigned_ids == {"a", "b"}  # должен выбрать совместимую пару, а не C


def test_matchmaker_too_few_candidates_raises():
    matchmaker = GenomeMatchmaker()
    a = AgentGenome(id="only-one", bias_control=80)
    _assert_raises(ValueError, lambda: matchmaker.best_team([a], roles=["executor", "reviewer"]))


# --- 5. Chain Risk Aggregator -------------------------------------------------

def test_chain_reliability_lower_than_average_would_suggest():
    step_a = AgentGenome(id="step-a", bias_control=90, transparency=90, data_safety=90, drift_rate=0.1, has_ledger=True)
    step_b = AgentGenome(id="step-b", bias_control=90, transparency=90, data_safety=90, drift_rate=0.1, has_ledger=True)
    aggregator = ChainRiskAggregator()
    result = aggregator.score_chain([step_a, step_b])
    avg_of_scores = sum(result.step_scores) / len(result.step_scores)
    assert result.chain_reliability < avg_of_scores  # произведение < среднего


def test_chain_identifies_weakest_link():
    strong = AgentGenome(id="strong", bias_control=95, transparency=95, data_safety=95, drift_rate=0.02, has_ledger=True)
    weak = AgentGenome(id="weak", bias_control=40, transparency=40, data_safety=40, drift_rate=0.5, has_ledger=False)
    result = ChainRiskAggregator().score_chain([strong, weak])
    assert result.weakest_link_id == "weak"


def test_chain_too_short_raises():
    a = AgentGenome(id="only", bias_control=80)
    _assert_raises(ValueError, lambda: ChainRiskAggregator().score_chain([a]))


# --- 6. Prompt-to-Genome Extractor (с мок-LLM, без реальной сети) -----------

def test_extractor_parses_clean_json():
    def mock_llm(prompt: str) -> str:
        return '{"transparency": 80, "bias_control": 75, "data_safety": 90, "domain": "support", "autonomy": "advisory"}'

    extractor = PromptToGenomeExtractor(llm_call=mock_llm)
    genome = extractor.extract(agent_id="test-agent", system_prompt="Ты дружелюбный ассистент поддержки.")
    assert genome.transparency == 80
    assert genome.domain == "support"


def test_extractor_handles_markdown_wrapped_json():
    def mock_llm(prompt: str) -> str:
        return '```json\n{"transparency": 70, "bias_control": 70, "data_safety": 70, "domain": null, "autonomy": "advisory"}\n```'

    extractor = PromptToGenomeExtractor(llm_call=mock_llm)
    genome = extractor.extract(agent_id="test-agent-2", system_prompt="...")
    assert genome.transparency == 70


def test_extractor_invalid_json_raises_extraction_error():
    def mock_llm(prompt: str) -> str:
        return "Извините, я не могу это проанализировать."

    extractor = PromptToGenomeExtractor(llm_call=mock_llm)
    _assert_raises(ExtractionError, lambda: extractor.extract(agent_id="bad", system_prompt="..."))


# --- 7. Reports --------------------------------------------------------------

def test_trust_report_contains_key_info():
    genome = AgentGenome(id="report-test", bias_control=70, transparency=70, data_safety=70, drift_rate=0.2, has_ledger=False)
    result = TrustScorer().score(genome)
    report = trust_report(result, agent_id="report-test")
    assert "report-test" in report
    assert str(result.score) in report
    assert result.label in report
    assert "Powered by Agenomics" in report  # атрибуция присутствует


def test_compatibility_report_contains_key_info():
    a = AgentGenome(id="a", bias_control=80, risk_tolerance=50, social_style=50)
    b = AgentGenome(id="b", bias_control=82, risk_tolerance=50, social_style=50)
    result = CompatibilityScorer().score_team([a, b])
    report = compatibility_report(result)
    assert "a" in report and "b" in report
    assert str(result.average_score) in report
