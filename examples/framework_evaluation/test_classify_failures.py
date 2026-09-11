"""
test_classify_failures.py. Тесты classify_failures.py.

Проект: Prizolov Lab
"""

import sys
sys.path.insert(0, ".")

from classify_failures import classify_error, build_failure_report


def test_classify_rate_limit():
    assert classify_error("litellm.RateLimitError: RateLimitError: GroqException") == "rate_limit"


def test_classify_import_error():
    assert classify_error("Framework x: ImportError: cannot import name 'Y'") == "import_error"
    assert classify_error("ModuleNotFoundError: No module named 'autogen'") == "import_error"


def test_classify_model_unavailable():
    assert classify_error("model llama-3.3-70b-versatile does not exist or you do not have access") == "model_unavailable"


def test_classify_auth_error():
    assert classify_error("No API key was provided. Please pass a valid API key.") == "auth_error"


def test_classify_provider_routing_error():
    assert classify_error("Cannot select auto-router when using non-Hugging Face API key.") == "provider_routing_error"


def test_classify_known_upstream_bug():
    assert classify_error("property 'cache_breakpoint' is unsupported") == "known_upstream_bug"


def test_classify_unrecognized_text_becomes_other():
    """Честная граница: неизвестный текст - "other", не выдуманная
    категория и не ошибка."""
    assert classify_error("Framework x: исключение при выполнении") == "other"


def test_classify_empty_description_becomes_other():
    assert classify_error("") == "other"
    assert classify_error(None) == "other"


def test_build_failure_report_counts_correctly():
    import tempfile, os
    sys.path.insert(0, "..")
    from agenomics import EvidenceStore, Incident, IncidentSeverity

    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = EvidenceStore(db_path)
        store.record_observation("agent-1", 0.0, "High Risk", incidents=[
            Incident("RateLimitError: hit limit", IncidentSeverity.SEVERE),
        ])
        store.record_observation("agent-1", 0.0, "High Risk", incidents=[
            Incident("ImportError: cannot import X", IncidentSeverity.SEVERE),
        ])
        store.close()

        report = build_failure_report(db_path)
        assert report["agent-1"]["rate_limit"] == 1
        assert report["agent-1"]["import_error"] == 1


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK:", t.__name__)
    print(f"\n{len(tests)}/{len(tests)} passed")
