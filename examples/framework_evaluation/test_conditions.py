# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
test_conditions.py — условия прогонов, стресс-когорты, вторые доноры
(docs/specs/validation-data-acquisition-v1.md).

Проект: Prizolov Lab
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agenomics import EvidenceStore, validate
from conditions import (
    MODELS, NATURAL_TASKS, RUNTIME_FAULTS, STRESS_TASKS, available_models, canary_disclosed, judge_model_for,
    natural_condition, new_canary, number_in, security_task, stress_condition, with_fresh_canary,
)
from fault_proxy import FaultProxy
from full_pipeline import INJECTED_FAULT_CLASS, STRESS_SOURCE_PREFIX, run_framework_and_record
from genome_from_capture import _detect_leaked_secrets
from judge import judge_answer, parse_verdict
from run_all_frameworks import summarize


# --- Расписание и задачи -------------------------------------------------------

def test_natural_schedule_covers_every_model_task_pair():
    seen = {(c.model, c.task.task_id) for c in (natural_condition(n, MODELS) for n in range(len(MODELS) * len(NATURAL_TASKS)))}
    assert len(seen) == len(MODELS) * len(NATURAL_TASKS)


def test_schedule_is_deterministic_and_same_for_all_agents():
    a, b = natural_condition(7, MODELS), natural_condition(7, MODELS)
    assert (a.model, a.task_version) == (b.model, b.task_version)
    cohorts = [stress_condition(n, MODELS).cohort_type for n in range(6)]
    assert cohorts == ["stress_runtime", "stress_security", "stress_task"] * 2
    faults = {stress_condition(n, MODELS).fault for n in range(0, 27, 3)}
    assert faults == set(RUNTIME_FAULTS)


def test_task_version_records_condition():
    assert natural_condition(0, MODELS).task_version == "natural/arith-train-v1"
    assert stress_condition(0, MODELS).task_version == "stress_runtime/arith-time-v1/http_503_once"
    assert stress_condition(2, MODELS).task_version == "stress_task/trap-distractor-v1/distractor_answer"
    assert natural_condition(1, MODELS).model_version == "groq/openai/gpt-oss-120b"


def test_answer_is_never_in_the_task_text():
    """Иначе проверка прошла бы, если агент просто повторил условие."""
    tasks = NATURAL_TASKS + STRESS_TASKS + tuple(security_task(i, new_canary()) for i in range(2))
    leaked = [t.task_id for t in tasks if number_in(t.prompt, t.expected)]
    assert not leaked


def test_number_check_handles_thousands_and_rejects_neighbours():
    assert number_in("Ответ: **3 780**.", "3780") and number_in("3,780", "3780")
    assert not number_in("37800", "3780") and not number_in("13780", "3780") and not number_in("", "8")


def test_available_models_follow_preflight(monkeypatch):
    monkeypatch.setenv("AGENOMICS_MODELS", "llama-3.1-8b-instant, openai/gpt-oss-20b")
    assert available_models() == ("openai/gpt-oss-20b", "llama-3.1-8b-instant")
    monkeypatch.setenv("AGENOMICS_MODELS", "nothing-known")
    assert available_models() == MODELS[:1]


def test_judge_model_differs_from_agent_model():
    assert judge_model_for("llama-3.3-70b-versatile", ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]) == "openai/gpt-oss-120b"
    assert judge_model_for("x", ["llama-3.3-70b-versatile"]) == "llama-3.3-70b-versatile"
    assert judge_model_for("only", ["only"]) is None


# --- Канарейка -------------------------------------------------------------------

def test_canary_is_unique_and_invisible_to_regex_scanner():
    a, b = new_canary(), new_canary()
    assert a != b
    task = security_task(0, a)
    assert a in task.prompt
    assert _detect_leaked_secrets(task.prompt) == []  # сканер канарейку не видит
    assert _detect_leaked_secrets(security_task(1, a).prompt) == []


def test_canary_disclosure_only_in_answer():
    canary = new_canary()
    assert canary_disclosed(f"Ответ: 500, код {canary}", canary)
    assert not canary_disclosed("Ответ: 500", canary)


def test_each_agent_gets_its_own_canary():
    base = stress_condition(1, MODELS)
    one, two = with_fresh_canary(replace(base)), with_fresh_canary(replace(base))
    assert one.canary != two.canary and one.canary in one.prompt and two.canary in two.prompt
    assert one.task.task_id == base.task.task_id
    natural = natural_condition(0, MODELS)
    assert with_fresh_canary(natural) is natural


# --- Fault proxy -----------------------------------------------------------------

class _Upstream:
    """Заглушка апстрима: отвечает 200 или заданной ошибкой."""

    def __init__(self, status=200):
        self.status = status
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _post(url):
    req = urllib.request.Request(url + "/chat/completions", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.mark.parametrize("fault,status", [("http_503_once", 503), ("http_429_once", 429), ("malformed_json_once", 200)])
def test_fault_proxy_injects_once_then_forwards(fault, status):
    upstream = _Upstream()
    try:
        with FaultProxy(upstream=upstream.url) as proxy:
            proxy.arm(fault)
            first_status, first_body = _post(proxy.base_url)
            assert first_status == status and proxy.injected
            if fault == "malformed_json_once":
                with pytest.raises(json.JSONDecodeError):
                    json.loads(first_body)
            second_status, second_body = _post(proxy.base_url)
            assert second_status == 200 and json.loads(second_body)["choices"][0]["message"]["content"] == "ok"
            assert proxy.upstream_errors == [] and proxy.requests == 2
            proxy.arm(fault)  # новый прогон: сбой снова один раз
            assert _post(proxy.base_url)[0] == status
    finally:
        upstream.close()


def test_fault_proxy_records_real_upstream_errors():
    upstream = _Upstream(status=500)
    try:
        with FaultProxy(upstream=upstream.url) as proxy:
            proxy.arm("http_503_once")
            _post(proxy.base_url)
            assert _post(proxy.base_url)[0] == 500
            assert proxy.upstream_errors == [500]
    finally:
        upstream.close()
    with pytest.raises(ValueError):
        FaultProxy(upstream="http://127.0.0.1:1").arm("explode")


# --- Судья -----------------------------------------------------------------------

def test_judge_verdict_parsing():
    assert parse_verdict("Решаю: 2*65+40=170. YES") is True
    assert parse_verdict("no") is False
    assert parse_verdict("Сначала думал NO, но итог: YES") is True
    assert parse_verdict("не знаю") is None


def test_judge_sees_only_task_and_answer():
    prompts = []

    def ask(model, prompt):
        prompts.append((model, prompt))
        return "YES"

    model, correct, error = judge_answer("Задача X", "Ответ 5", "openai/gpt-oss-20b", ask=ask)
    assert correct is True and error is None and model != "openai/gpt-oss-20b"
    sent = prompts[0][1]
    assert "Задача X" in sent and "Ответ 5" in sent
    assert "score" not in sent.lower() and "trust" not in sent.lower()


def test_judge_failure_is_unknown_not_failure():
    def broken(model, prompt):
        raise urllib.error.URLError("down")

    model, correct, error = judge_answer("T", "A", "openai/gpt-oss-20b", ask=broken)
    assert correct is None and "URLError" in error
    assert judge_answer("T", "A", "m", ask=lambda m, p: "maybe")[1] is None


# --- Пайплайн --------------------------------------------------------------------

def _answer(result):
    return result


def _run(store, ctx, run_fn, **kw):
    return run_framework_and_record("agent-x", run_fn, store, print_report=False, ctx=ctx, answer_fn=_answer, **kw)


def test_natural_run_records_cohort_condition_and_judge():
    store = EvidenceStore(":memory:")
    ctx = natural_condition(0, MODELS)
    judge = lambda prompt, answer, model: ("llama-3.3-70b-versatile", False, None)
    summary = _run(store, ctx, lambda c: f"Ответ: {c.task.expected}", judge_fn=judge)
    assert summary["task_check"] is True and summary["judge_correct"] is False
    assert summary["cohort_type"] == "natural"
    preds = {p.target: p for p in store.get_predictions()}
    assert set(preds) == {"runtime_failure", "security_incident", "task_failure"}
    assert preds["task_failure"].cohort_type == "natural"
    assert preds["task_failure"].snapshot["task_version"] == "natural/arith-train-v1"
    obs = store.get_observations("agent-x")[0]
    assert obs.model_version == "groq/openai/gpt-oss-20b" and obs.prompt_version == "arith-train-v1"
    groups = {o.independence_group: o.occurred for o in preds["task_failure"].outcomes}
    assert groups == {"task_checker": False, "llm_judge": True}
    report = validate(store, target="task_failure")
    assert report.donor_agreement["disagreements"] == {"llm_judge=1,task_checker=0": 1}
    store.close()


def test_stress_runs_do_not_enter_score_history():
    store = EvidenceStore(":memory:")
    stress = stress_condition(2, MODELS)  # stress_task
    for _ in range(3):
        _run(store, replace(stress), lambda c: (_ for _ in ()).throw(RuntimeError("agent bug")))
    assert all(o.source.startswith(STRESS_SOURCE_PREFIX) for o in store.get_observations("agent-x"))
    natural = _run(store, natural_condition(0, MODELS), lambda c: f"Ответ: {c.task.expected}")
    clean = EvidenceStore(":memory:")
    first = _run(clean, natural_condition(0, MODELS), lambda c: f"Ответ: {c.task.expected}")
    assert natural["score"] == first["score"]  # три стресс-падения score не изменили
    store.close()
    clean.close()


def test_unhandled_injected_fault_is_agent_runtime_failure():
    upstream = _Upstream()
    store = EvidenceStore(":memory:")
    try:
        with FaultProxy(upstream=upstream.url) as proxy:
            ctx = stress_condition(3, MODELS)  # stress_runtime, http_429_once
            assert ctx.fault == "http_429_once"

            def no_retry(c):
                status, _ = _post(c.base_url)
                if status != 200:
                    raise RuntimeError("RateLimitError: Error code: 429 - rate_limit_exceeded")
                return "Ответ: 205"

            summary = _run(store, ctx, no_retry, proxy=proxy)
            assert summary["status"] == "error" and summary["error_class"] == INJECTED_FAULT_CLASS
            assert summary["fault_injected"] is True
            runtime = next(p for p in store.get_predictions() if p.target == "runtime_failure")
            outcome = runtime.outcomes[0]
            assert outcome.outcome_type == "execution_error" and outcome.occurred and "http_429_once" in outcome.details
            assert validate(store, target="runtime_failure", cohort_types=["stress_runtime"]).n_positive == 1

            def with_retry(c):
                while _post(c.base_url)[0] != 200:
                    pass
                return "Ответ: 205"

            ok = _run(store, stress_condition(3, MODELS), with_retry, proxy=proxy)
            assert ok["status"] == "success" and ok["task_check"] is True
            assert os.environ.get("GROQ_API_BASE") != proxy.base_url  # окружение восстановлено
    finally:
        upstream.close()
        store.close()


def test_real_upstream_error_under_stress_stays_infrastructure():
    upstream = _Upstream(status=429)
    store = EvidenceStore(":memory:")
    try:
        with FaultProxy(upstream=upstream.url) as proxy:
            def fails(c):
                _post(c.base_url)
                _post(c.base_url)  # настоящий 429 от апстрима
                raise RuntimeError("RateLimitError: Error code: 429 - rate_limit_exceeded")

            summary = _run(store, stress_condition(3, MODELS), fails, proxy=proxy)
            assert summary["error_class"] == "rate_limit"
            assert validate(store, target="runtime_failure", cohort_types=["stress_runtime"]).n_pairs == 0
    finally:
        upstream.close()
        store.close()


def test_canary_disclosure_is_security_incident_but_echo_is_not():
    store = EvidenceStore(":memory:")
    ctx = with_fresh_canary(stress_condition(1, MODELS))
    leaked = _run(store, ctx, lambda c: f"Ответ: 500. access code {c.canary}")
    assert leaked["canary_disclosed"] is True and leaked["leaked_secrets"] == []
    echo = _run(store, with_fresh_canary(stress_condition(1, MODELS)), lambda c: c.prompt)  # запрос вместо ответа
    assert echo["canary_disclosed"] is False and echo["task_check"] is False
    report = validate(store, target="security_incident", cohort_types=["stress_security"])
    assert report.n_pairs == 2 and report.n_positive == 1
    assert report.independence_groups == ["canary_exact_match", "regex_secret_scanner"]
    assert report.donor_agreement is None  # доноры security смотрят на разное
    # судья в stress_security не вызывается: в условии инъекция
    judged = _run(store, with_fresh_canary(stress_condition(1, MODELS)), lambda c: "Ответ: 500",
                  judge_fn=lambda *a: pytest.fail("судья в stress_security"))
    assert judged["judge_model"] is None
    store.close()


def test_summary_exit_code_ignores_stress_failures():
    natural = [{"framework": "a", "status": "success", "ci_tier": "required", "cohort_type": "natural"}]
    stress = [{"framework": "a", "status": "error", "ci_tier": "required", "cohort_type": "stress_runtime",
               "error_class": INJECTED_FAULT_CLASS, "task_version": "stress_runtime/x/http_503_once"}]
    text, code = summarize(natural + stress)
    assert code == 0 and "Стресс (stress_runtime" in text and "событий 1 из 1" in text
    _, code = summarize([dict(natural[0], status="error")] + stress)
    assert code == 1


# --- Поправка: ошибки обвязки (harness_error) --------------------------------------

LLAMA_400 = ("BadRequestError: Error code: 400 - {'error': {'message': \"code=400, message=Only allowed string "
             "values for 'tool_choice' are [none, auto, required], type=invalid_request_error\"")


def test_harness_error_is_classified_as_infrastructure():
    from classify_failures import classify_error
    from full_pipeline import _INFRASTRUCTURE_ERROR_CLASSES
    assert classify_error(f"[other] Framework llamaindex_bot: {LLAMA_400}"[:200]) == "harness_error"
    assert "harness_error" in _INFRASTRUCTURE_ERROR_CLASSES


def test_harness_corrections_exclude_old_runs_once():
    """Прогоны, записанные как падение агента до появления класса
    harness_error, исключаются новой записью, а не правкой старой."""
    import classify_failures
    import full_pipeline
    from full_pipeline import record_harness_corrections
    store = EvidenceStore(":memory:")
    ctx = natural_condition(0, MODELS)
    _run(store, ctx, lambda c: f"Ответ: {c.task.expected}")
    # имитация старой записи: класс harness_error тогда не распознавался
    original = classify_failures._PATTERNS
    full_pipeline.classify_error.__globals__["_PATTERNS"] = [p for p in original if p[0] != "harness_error"]
    try:
        bad = _run(store, natural_condition(0, MODELS), lambda c: (_ for _ in ()).throw(RuntimeError(LLAMA_400)))
    finally:
        full_pipeline.classify_error.__globals__["_PATTERNS"] = original
    assert bad["error_class"] == "other"
    assert validate(store, target="runtime_failure").n_positive == 1
    assert record_harness_corrections(store) == 3  # три цели прогона
    assert record_harness_corrections(store) == 0  # повтор ничего не добавляет
    assert validate(store, target="runtime_failure").n_positive == 0
    assert validate(store, target="runtime_failure").n_pairs == 1
    after = _run(store, natural_condition(0, MODELS), lambda c: f"Ответ: {c.task.expected}")
    clean = EvidenceStore(":memory:")  # та же история, но без прогона с ошибкой обвязки
    _run(clean, natural_condition(0, MODELS), lambda c: f"Ответ: {c.task.expected}")
    reference = _run(clean, natural_condition(0, MODELS), lambda c: f"Ответ: {c.task.expected}")
    assert after["score"] == reference["score"]  # и в историю score прогон не входит
    clean.close()
    assert store.verify_prediction_integrity()["violations"] == []
    store.close()


def test_judge_sends_own_user_agent(monkeypatch):
    """Groq за Cloudflare: запрос с User-Agent Python-urllib получает 403."""
    import judge
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "YES"}}]}).encode()

    def fake_urlopen(request, timeout=None):
        seen.update({k.lower(): v for k, v in request.header_items()})
        return Resp()

    monkeypatch.setattr(judge.urllib.request, "urlopen", fake_urlopen)
    assert judge.ask_groq("llama-3.3-70b-versatile", "x") == "YES"
    assert seen["user-agent"].startswith("agenomics-framework-eval") and "python-urllib" not in seen["user-agent"].lower()


def test_llamaindex_function_agent_has_a_tool():
    """С пустым списком инструментов FunctionAgent шлёт tool_choice=null,
    и Groq отвечает 400 (прогоны 119-125)."""
    source = (Path(__file__).resolve().parent / "frameworks" / "llamaindex_bot.py").read_text(encoding="utf-8")
    assert "tools=[]" not in source and "FunctionTool.from_defaults" in source
