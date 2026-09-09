"""
test_extractor.py. Тесты PromptToGenomeExtractor.

Проект: Prizolov Lab
"""

from agenomics import PromptToGenomeExtractor, AgentGenome
from agenomics.extractor import ExtractionError


def _fake_llm_full():
    def call(prompt):
        return '{"transparency": 70, "bias_control": 80, "data_safety": 60, "domain": "content", "autonomy": "advisory"}'
    return call


def test_extract_builds_genome_from_llm_response():
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_full())
    genome = extractor.extract(agent_id="test", system_prompt="...")
    assert genome.domain == "content"
    assert genome.transparency == 70
    assert genome.bias_control == 80
    assert genome.data_safety == 60
    assert genome.autonomy == "advisory"


def test_genome_override_of_extracted_field_does_not_crash():
    """Регрессионный тест на реальный баг: переопределение domain (или
    любой другой извлечённой оси) через genome_overrides падало с
    'got multiple values for keyword argument', потому что то же поле
    уже передавалось явно перед **genome_overrides."""
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_full())
    genome = extractor.extract(agent_id="test", system_prompt="...", domain="finance")
    assert genome.domain == "finance"


def test_genome_override_of_autonomy_does_not_crash():
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_full())
    genome = extractor.extract(agent_id="test", system_prompt="...", autonomy="autonomous")
    assert genome.autonomy == "autonomous"


def test_genome_override_of_numeric_axis_does_not_crash():
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_full())
    genome = extractor.extract(agent_id="test", system_prompt="...", bias_control=95)
    assert genome.bias_control == 95


def test_additional_field_not_returned_by_llm_can_be_set():
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_full())
    genome = extractor.extract(agent_id="test", system_prompt="...", has_ledger=True)
    assert genome.has_ledger is True


def test_markdown_wrapped_json_is_parsed():
    def call(prompt):
        return '```json\n{"transparency": 50, "bias_control": 50, "data_safety": 50, "domain": "content", "autonomy": "advisory"}\n```'
    extractor = PromptToGenomeExtractor(llm_call=call)
    genome = extractor.extract(agent_id="test", system_prompt="...")
    assert genome.transparency == 50


def test_invalid_json_raises_extraction_error():
    def call(prompt):
        return "это не JSON вообще"
    extractor = PromptToGenomeExtractor(llm_call=call)
    try:
        extractor.extract(agent_id="test", system_prompt="...")
        assert False, "должно было выбросить ExtractionError"
    except ExtractionError:
        pass


def _fake_llm_structured():
    def call(prompt):
        return (
            '{"transparency": {"value": 75, "confidence": 0.8, "evidence": "quote A"}, '
            '"bias_control": {"value": 60, "confidence": 0.4, "evidence": "quote B"}, '
            '"data_safety": {"value": null, "confidence": 0.0, "evidence": "no mention"}, '
            '"domain": "support", "autonomy": "advisory"}'
        )
    return call


def test_structured_format_populates_axis_confidence():
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_structured())
    genome = extractor.extract(agent_id="test", system_prompt="...")
    assert genome.transparency == 75
    assert genome.axis_confidence == {"transparency": 0.8, "bias_control": 0.4, "data_safety": 0.0}


def test_structured_format_null_value_stays_none():
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_structured())
    genome = extractor.extract(agent_id="test", system_prompt="...")
    assert genome.data_safety is None  # null остаётся None, не превращается в 0


def test_extract_with_evidence_returns_evidence_text():
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_structured())
    result = extractor.extract_with_evidence(agent_id="test", system_prompt="...")
    assert result.genome.transparency == 75
    assert result.evidence["transparency"].evidence == "quote A"
    assert result.evidence["transparency"].confidence == 0.8


def test_flat_format_evidence_has_no_confidence_or_text():
    """Обратная совместимость: старый плоский формат не имеет evidence,
    и мы не придумываем его задним числом."""
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_full())
    result = extractor.extract_with_evidence(agent_id="test", system_prompt="...")
    assert result.evidence["transparency"].value == 70
    assert result.evidence["transparency"].confidence is None
    assert result.evidence["transparency"].evidence is None


def test_extract_still_returns_plain_genome_for_backward_compat():
    """extract() должен возвращать AgentGenome напрямую, не обёртку,
    иначе сломался бы весь код, написанный до v0.7.5."""
    extractor = PromptToGenomeExtractor(llm_call=_fake_llm_full())
    genome = extractor.extract(agent_id="test", system_prompt="...")
    assert isinstance(genome, AgentGenome)


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK:", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} passed")
