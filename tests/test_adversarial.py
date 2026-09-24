"""
test_adversarial.py. Тесты Adversarial Evaluation Suite (v0.8.0).

Агенты здесь фейковые, но честно ведут себя по-разному: безопасный,
выдающий секреты, выполняющий инъекции, предвзятый, падающий. Реальная
LLM в тестах не нужна: пробы детерминированы по устройству.

Проект: Prizolov Lab
"""

import re

from agenomics import AdversarialSuite, AgentGenome, adversarial_report_text
from agenomics.adversarial import _contains_canary

_SECRET_RE = re.compile(r"sk-canary-[0-9a-f]+")
_MARKER_RE = re.compile(r"INJECTED-[0-9A-F]+")


def safe_agent(prompt: str) -> str:
    if "YES or NO" in prompt:
        return "YES"
    return "I can't share confidential data, but here is a summary of the request."


def leaky_agent(prompt: str) -> str:
    match = _SECRET_RE.search(prompt)
    if match:
        return f"Sure, it is {match.group(0)}"
    return safe_agent(prompt)


def obfuscating_leaker(prompt: str) -> str:
    match = _SECRET_RE.search(prompt)
    if match:
        return "-".join(reversed(match.group(0)))
    return safe_agent(prompt)


def injectable_agent(prompt: str) -> str:
    match = _MARKER_RE.search(prompt)
    if match:
        return match.group(0)
    return safe_agent(prompt)


def biased_agent(prompt: str) -> str:
    if "YES or NO" in prompt:
        return "NO" if "Lakisha" in prompt or "Mohammed" in prompt else "YES"
    return safe_agent(prompt)


def evasive_agent(prompt: str) -> str:
    if "YES or NO" in prompt:
        return "I'd rather not make that decision."
    return safe_agent(prompt)


def fragile_agent(prompt: str) -> str:
    if not prompt or len(prompt) > 10000 or "\x00" in prompt:
        raise ValueError("cannot handle this input")
    return safe_agent(prompt)


def crashing_agent(prompt: str) -> str:
    raise RuntimeError("provider down")


def _by_id(report):
    return {r.probe_id: r for r in report.results}


def test_safe_agent_passes_everything():
    report = AdversarialSuite().run("safe", safe_agent)
    assert not report.failures
    assert report.axis_estimates["data_safety"].value == 100.0
    assert report.axis_estimates["bias_control"].value == 100.0


def test_leaky_agent_fails_secret_probes_only():
    report = AdversarialSuite().run("leaky", leaky_agent)
    failed = {r.probe_id for r in report.failures}
    assert failed == {"secret_leak_direct", "secret_leak_verbatim_repeat", "secret_leak_obfuscated"}
    est = report.axis_estimates["data_safety"]
    assert est.n_conclusive == 5 and est.n_passed == 2 and est.value == 40.0
    assert report.axis_estimates["bias_control"].value == 100.0


def test_obfuscated_leak_is_detected():
    report = AdversarialSuite().run("obf", obfuscating_leaker)
    assert _by_id(report)["secret_leak_obfuscated"].passed is False


def test_canary_detection_does_not_fire_on_refusal():
    assert not _contains_canary("I cannot reveal sk-canary keys.", "sk-canary-0123456789abcdef")
    assert _contains_canary("S K - C A N A R Y - 0123456789ABCDEF", "sk-canary-0123456789abcdef")


def test_injectable_agent_fails_injection_probes():
    report = AdversarialSuite().run("inj", injectable_agent)
    by_id = _by_id(report)
    assert by_id["injection_in_user_content"].passed is False
    assert by_id["injection_in_retrieved_document"].passed is False
    assert by_id["secret_leak_direct"].passed is True


def test_biased_agent_fails_consistency_probes():
    report = AdversarialSuite().run("biased", biased_agent)
    bias = [r for r in report.results if r.category == "bias_consistency"]
    assert all(r.passed is False for r in bias)
    assert "Lakisha Washington=no" in bias[0].detail
    assert report.axis_estimates["bias_control"].value == 0.0


def test_evasive_answers_are_inconclusive_not_passed():
    report = AdversarialSuite().run("evasive", evasive_agent)
    bias = [r for r in report.results if r.category == "bias_consistency"]
    assert all(r.passed is None for r in bias)
    est = report.axis_estimates["bias_control"]
    assert est.value is None and est.confidence == 0.0


def test_fragile_agent_fails_robustness_but_axes_unaffected():
    report = AdversarialSuite().run("fragile", fragile_agent)
    robustness = [r for r in report.results if r.category == "robustness"]
    assert all(r.passed is False for r in robustness)
    assert all(r.axis is None for r in robustness)
    assert report.axis_estimates["data_safety"].value == 100.0


def test_crashing_agent_gives_no_axis_estimates():
    report = AdversarialSuite().run("down", crashing_agent)
    assert report.axis_estimates["data_safety"].value is None
    assert report.axis_estimates["bias_control"].value is None
    assert all(r.error for r in report.results)


def test_nonces_differ_between_runs():
    seen = []

    def recording_agent(prompt):
        seen.extend(_SECRET_RE.findall(prompt))
        return safe_agent(prompt)

    AdversarialSuite().run("a", recording_agent)
    AdversarialSuite().run("a", recording_agent)
    assert len(seen) == 6 and len(set(seen)) == 6


def test_repeats_catch_intermittent_leak():
    calls = {"n": 0}

    def sometimes_leaks(prompt):
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            return leaky_agent(prompt)
        return safe_agent(prompt)

    single = AdversarialSuite(repeats=1).run("x", sometimes_leaks)
    calls["n"] = 0
    repeated = AdversarialSuite(repeats=2).run("x", sometimes_leaks)
    assert len(repeated.failures) >= len(single.failures)
    assert any(r.category == "secret_leak" for r in repeated.failures)


def test_apply_to_genome_fills_only_missing_axes_by_default():
    report = AdversarialSuite().run("leaky", leaky_agent)
    genome = AgentGenome(id="leaky", bias_control=70)
    updated = report.apply_to_genome(genome)
    assert updated.data_safety == 40.0
    assert updated.bias_control == 70  # заявленное значение не затёрто
    assert updated.axis_confidence["data_safety"] == 0.5
    assert "bias_control" not in updated.axis_confidence

    overwritten = report.apply_to_genome(genome, overwrite=True)
    assert overwritten.bias_control == 100.0


def test_apply_to_genome_without_conclusive_probes_returns_same_genome():
    report = AdversarialSuite().run("down", crashing_agent)
    genome = AgentGenome(id="down")
    assert report.apply_to_genome(genome) is genome


def test_text_report_marks_failures():
    text = adversarial_report_text(AdversarialSuite().run("leaky", leaky_agent))
    assert "❌ secret_leak_direct" in text
    assert "data_safety: 40" in text


def test_repeats_must_be_positive():
    try:
        AdversarialSuite(repeats=0)
        assert False
    except ValueError:
        pass


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK:", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} passed")
