# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
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



# --- Строгая валидация (v0.8.0) ------------------------------------------

def _extractor_returning(payload: str, strict: bool = True):
    return PromptToGenomeExtractor(llm_call=lambda prompt: payload, strict=strict)


def _violations_for(payload: str):
    try:
        _extractor_returning(payload).extract(agent_id="t", system_prompt="...")
    except ExtractionError as e:
        return e.violations
    return []


def test_strict_collects_all_violations_not_only_first():
    violations = _violations_for(
        '{"transparency": 150, "bias_control": "high", "data_safety": 50, "autonomy": "yolo", "notes": "x"}'
    )
    joined = " | ".join(violations)
    assert "transparency" in joined and "150" in joined
    assert "bias_control" in joined
    assert "autonomy" in joined
    assert "notes: неизвестное поле" in joined
    assert len(violations) == 4


def test_strict_rejects_bool_as_axis_value():
    assert _violations_for('{"transparency": true, "bias_control": 50, "data_safety": 50}')


def test_strict_rejects_missing_axis():
    violations = _violations_for('{"transparency": 50, "bias_control": 50}')
    assert any("data_safety" in v and "отсутствует" in v for v in violations)


def test_strict_structured_requires_evidence_and_valid_confidence():
    violations = _violations_for(
        '{"transparency": {"value": 70, "confidence": 1.4, "evidence": ""}, '
        '"bias_control": {"value": 70, "confidence": 0.5}, "data_safety": null}'
    )
    joined = " | ".join(violations)
    assert "transparency.confidence" in joined
    assert "transparency.evidence" in joined
    assert "bias_control.evidence: обязательное поле отсутствует" in joined


def test_strict_rejects_confident_null_value():
    violations = _violations_for(
        '{"transparency": {"value": null, "confidence": 0.9, "evidence": "guess"}, '
        '"bias_control": 50, "data_safety": 50}'
    )
    assert any("value=null" in v for v in violations)


def test_strict_rejects_non_object_response():
    assert _violations_for("[1, 2, 3]")


def test_valid_responses_pass_strict():
    assert _violations_for('{"transparency": 70, "bias_control": 80, "data_safety": 60, "domain": "content", "autonomy": "advisory"}') == []
    assert _violations_for(
        '{"transparency": {"value": 75, "confidence": 0.8, "evidence": "quote A"}, '
        '"bias_control": {"value": 60, "confidence": 0.4, "evidence": "quote B"}, '
        '"data_safety": {"value": null, "confidence": 0.0, "evidence": "no mention"}, '
        '"domain": "support", "autonomy": "advisory"}'
    ) == []


def test_non_strict_keeps_pre_080_behaviour_for_unknown_fields():
    genome = _extractor_returning(
        '{"transparency": 70, "bias_control": 80, "data_safety": 60, "notes": "ignored"}', strict=False
    ).extract(agent_id="t", system_prompt="...")
    assert genome.transparency == 70


def test_json_schema_agrees_with_stdlib_validator():
    """EXTRACTION_JSON_SCHEMA и validate_extraction_payload() должны
    описывать одни и те же структурные правила. Проверяется, только если
    установлен jsonschema (dev-зависимость, не runtime)."""
    try:
        import jsonschema
    except ImportError:
        return
    from agenomics import EXTRACTION_JSON_SCHEMA, validate_extraction_payload
    import json
    cases = [
        '{"transparency": 70, "bias_control": 80, "data_safety": 60}',
        '{"transparency": 150, "bias_control": 80, "data_safety": 60}',
        '{"transparency": 70, "bias_control": 80}',
        '{"transparency": 70, "bias_control": 80, "data_safety": 60, "extra": 1}',
        '{"transparency": 70, "bias_control": 80, "data_safety": 60, "autonomy": "yolo"}',
        '{"transparency": {"value": 70, "confidence": 0.5, "evidence": "q"}, "bias_control": null, "data_safety": 1}',
        '{"transparency": {"value": 70, "confidence": 2, "evidence": "q"}, "bias_control": null, "data_safety": 1}',
        '{"transparency": {"value": 70, "confidence": 0.5}, "bias_control": null, "data_safety": 1}',
    ]
    for case in cases:
        data = json.loads(case)
        schema_valid = jsonschema.Draft202012Validator(EXTRACTION_JSON_SCHEMA).is_valid(data)
        stdlib_valid = not validate_extraction_payload(data)
        assert schema_valid == stdlib_valid, case


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK:", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} passed")
