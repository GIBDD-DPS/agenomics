# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""Тесты полного пайплайна capture_log_v2 -> genome_from_capture -> EvidenceStore."""

import sys
from pathlib import Path
sys.path.insert(0, ".")

from agenomics import EvidenceStore
from full_pipeline import run_framework_and_record
from genome_from_capture import _detect_leaked_secrets, derive_genome_from_capture


def test_secret_detection_openai_key():
    log = 'api_key: sk-proj-abcdefghijklmnopqrstuvwxyz123456'
    assert "openai_style_key" in _detect_leaked_secrets(log)


def test_secret_detection_bearer_token():
    log = 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234567890'
    assert "bearer_token" in _detect_leaked_secrets(log)


def test_secret_detection_json_format():
    log = '{"api_key": "sk-1234567890abcdefghijklmnop"}'
    found = _detect_leaked_secrets(log)
    assert "openai_style_key" in found
    assert "generic_api_key_assignment" in found


def test_no_false_positive_on_clean_log():
    log = "INFO: Task completed successfully\nDEBUG: Processing item 42"
    assert _detect_leaked_secrets(log) == []


def test_derived_genome_leaves_bias_control_none():
    """Ключевая проверка честности: bias_control НЕ должен подставляться,
    его нельзя вывести из лога выполнения."""
    result = derive_genome_from_capture("x", "some log", domain="content", autonomy="advisory")
    assert result.genome.bias_control is None
    assert result.genome.transparency is None


def test_derived_genome_has_ledger_false_by_default():
    """[v0.7.2, исправление после внешнего разбора] has_ledger больше НЕ
    True по умолчанию: capture_log сам по себе не делает фреймворк
    обладателем настоящего audit trail."""
    result = derive_genome_from_capture("x", "log", domain="content", autonomy="advisory")
    assert result.genome.has_ledger is False


def test_has_ledger_can_be_explicitly_asserted_true():
    result = derive_genome_from_capture("x", "log", domain="content", autonomy="advisory", has_ledger=True)
    assert result.genome.has_ledger is True


def test_predictability_requires_three_runs():
    result_1run = derive_genome_from_capture(
        "x", "log", framework_history_statuses=["success"], framework_history_durations=[1.0]
    )
    assert result_1run.genome.drift_rate is None

    result_3runs = derive_genome_from_capture(
        "x", "log",
        framework_history_statuses=["success", "error", "success"],
        framework_history_durations=[1.0, 1.5, 0.9],
    )
    assert result_3runs.genome.drift_rate is not None


def test_full_pipeline_records_observation():
    store = EvidenceStore(":memory:")

    def clean_run():
        print("OK")

    summary = run_framework_and_record("test-fw", clean_run, store, domain="content", print_report=False)
    assert summary["status"] == "success"
    assert store.count_observations("test-fw") == 1
    obs = store.get_observations("test-fw")[0]
    assert obs.genome_hash is not None
    store.close()


def test_full_pipeline_crash_becomes_confirmed_incident():
    store = EvidenceStore(":memory:")

    def crashing_run():
        raise ValueError("boom")

    summary = run_framework_and_record("crash-fw", crashing_run, store, domain="content", print_report=False)
    assert summary["status"] == "error"
    obs = store.get_observations("crash-fw")[0]
    assert len(obs.incidents) == 1
    assert obs.incidents[0]["confirmed"] is True
    assert obs.incidents[0]["severity"] == "severe"
    # Регрессия: раньше описание было шаблонным ("исключение при
    # выполнении") без текста самой ошибки, из базы было невозможно
    # понять причину падения. Теперь реальный текст исключения обязан
    # попадать в description.
    assert "ValueError" in obs.incidents[0]["description"]
    assert "boom" in obs.incidents[0]["description"]
    store.close()


def test_full_pipeline_leak_becomes_data_leak_incident():
    store = EvidenceStore(":memory:")

    def leaking_run():
        print('token: Bearer abcdefghijklmnopqrstuvwxyz1234567890')

    run_framework_and_record("leak-fw", leaking_run, store, domain="content", print_report=False)
    obs = store.get_observations("leak-fw")[0]
    assert any(inc["category"] == "data_leak" for inc in obs.incidents)
    store.close()


def test_history_persists_across_separate_evidence_store_objects():
    """[v0.7.2, ключевой регрессионный тест] Имитация реального сценария
    GitHub Actions: КАЖДЫЙ вызов run_framework_and_record идёт с НОВЫМ
    объектом EvidenceStore на том же файле (как между отдельными
    процессами). История не должна теряться. Раньше (баг, найденный
    внешним разбором) она хранилась в module-level _HISTORY и терялась
    при каждом новом процессе."""
    import tempfile

    def sometimes_fails():
        import random
        if random.random() < 0.5:
            raise RuntimeError("boom")
        print("ok")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = f"{tmp}/restart.db"
        for _ in range(5):
            store = EvidenceStore(db_path)  # "новый процесс"
            run_framework_and_record("restart-fw", sometimes_fails, store, domain="content", print_report=False)
            store.close()  # "процесс завершился". Если бы история была в памяти, она бы тут пропала

        final_store = EvidenceStore(db_path)
        observations = final_store.get_observations("restart-fw")
        assert len(observations) == 5
        # Все execution_status должны быть реально сохранены персистентно
        assert all(o.execution_status in ("success", "error") for o in observations)
        final_store.close()



def test_full_pipeline_records_model_and_prompt_version():
    store = EvidenceStore(":memory:")
    run_framework_and_record(
        "versioned-fw", lambda: None, store, print_report=False,
        model_version="groq/openai/gpt-oss-20b", prompt_version="p1",
    )
    obs = store.get_observations("versioned-fw")[0]
    assert obs.model_version == "groq/openai/gpt-oss-20b"
    assert obs.prompt_version == "p1"
    store.close()


def _framework_templates():
    from pathlib import Path
    frameworks_dir = Path(__file__).resolve().parent / "frameworks"
    return [p for p in sorted(frameworks_dir.glob("*.py")) if not p.name.startswith("_")]


def _module_constant(source: str, name: str):
    """Читает строковую константу модуля через ast, без импорта:
    импорт шаблона не нужен и не должен зависеть от установленных
    фреймворков."""
    import ast
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ) and isinstance(node.value, ast.Constant):
            return node.value.value
    return None


def test_every_framework_template_declares_model_version():
    templates = _framework_templates()
    assert len(templates) >= 19
    missing = [p.name for p in templates if not _module_constant(p.read_text(encoding="utf-8"), "MODEL_VERSION")]
    assert not missing, f"MODEL_VERSION не объявлен в: {missing}"


def test_model_version_matches_model_actually_called():
    """MODEL_VERSION = "<провайдер>/<модель>". Идентификатор модели
    (всё после провайдера) обязан встречаться в коде шаблона ещё раз,
    помимо самой константы. Ловит ситуацию, когда модель в run()
    поменяли, а MODEL_VERSION забыли, и в EvidenceStore пишется
    неправда."""
    mismatched = []
    for p in _framework_templates():
        source = p.read_text(encoding="utf-8")
        model_version = _module_constant(source, "MODEL_VERSION")
        _, _, model_id = model_version.partition("/")
        declaration = next(line for line in source.splitlines() if line.startswith("MODEL_VERSION"))
        if not model_id or model_id not in source.replace(declaration, ""):
            mismatched.append(f"{p.name}: {model_version}")
    assert not mismatched, f"MODEL_VERSION не совпадает с моделью в run(): {mismatched}"


def test_runner_passes_model_version_from_template():
    from run_all_frameworks import discover_frameworks
    discovered = discover_frameworks()
    assert discovered["langchain_bot"]["model_version"] == "groq/openai/gpt-oss-20b"
    assert discovered["google_adk_bot"]["model_version"] == "google/gemini-2.5-flash"
    assert discovered["langchain_bot"]["prompt_version"] is None




# --- Задачи с проверяемым ответом (v0.9.4) ------------------------------

def _check_answer(source: str) -> str:
    import re
    return re.search(r"\(\?<!\\d\)(\d+)\(\?!\\d\)", source).group(1)


def test_every_framework_template_has_check():
    """С 0.9.4 у каждого шаблона задача с однозначным ответом и check():
    без него task_failure у агента не измеряется вовсе."""
    missing = [p.name for p in _framework_templates() if "\ndef check(result)" not in p.read_text(encoding="utf-8")]
    assert not missing, f"нет check(): {missing}"


def test_task_answer_is_not_in_task_text():
    """Ответ не должен стоять в условии: иначе check() пройдёт, если агент
    просто повторит вопрос (swarms, например, может вернуть всю историю
    диалога вместе с текстом задачи)."""
    import ast
    import re
    leaked = []
    for p in _framework_templates():
        source = p.read_text(encoding="utf-8")
        if "Ответь одним числом" not in source:
            continue
        answer = _check_answer(source)
        tasks = [n.value for n in ast.walk(ast.parse(source))
                 if isinstance(n, ast.Constant) and isinstance(n.value, str) and "Ответь одним числом" in n.value]
        assert tasks, p.name
        if any(re.search(rf"(?<!\d){answer}(?!\d)", t) for t in tasks):
            leaked.append(p.name)
    assert not leaked, f"ответ есть в условии задачи: {leaked}"


def test_checks_read_final_answer_of_each_framework():
    """check() каждого шаблона на результате той формы, которую возвращает
    его фреймворк: правильный ответ (в том числе с разрядами "1 800"),
    неправильный и пустой."""
    from types import SimpleNamespace as NS
    from run_all_frameworks import discover_frameworks

    shapes = {
        "agno_bot": lambda t: NS(content=t),
        "atomic_agents_bot": lambda t: NS(chat_message=t),
        "autogen_bot": lambda t: NS(summary=None, messages=[{"role": "user", "content": "q"}, {"content": t}]),
        "beeai_bot": lambda t: NS(result=NS(text=t)),
        "camel_bot": lambda t: NS(msgs=[NS(content=t)]),
        "crewai_bot": lambda t: NS(raw=t),
        "google_adk_bot": lambda t: [NS(content=NS(parts=[NS(text="думаю")])), NS(content=None),
                                     NS(content=NS(parts=[NS(text=t)]))],
        "griptape_bot": lambda t: NS(value=t),
        "haystack_bot": lambda t: {"last_message": NS(text=t), "messages": []},
        "langgraph_bot": lambda t: {"messages": [NS(content="q"), NS(content=t)]},
        "openai_agents_bot": lambda t: NS(final_output=t),
        "pydantic_ai_bot": lambda t: NS(output=t),
        "semantic_kernel_bot": lambda t: NS(content=t),
        "swarms_bot": lambda t: t,
        "txtai_bot": lambda t: t,
    }
    discovered = discover_frameworks()
    for name, shape in shapes.items():
        check = discovered[name]["check"]
        answer = _check_answer((Path(__file__).resolve().parent / "frameworks" / f"{name}.py").read_text(encoding="utf-8"))
        spaced = f"{answer[:-3]} {answer[-3:]}" if len(answer) > 3 else answer
        assert check(shape(f"Ответ: **{spaced}**.")), name
        assert not check(shape(f"Ответ: {int(answer) + 1}")), name
        assert not check(shape(f"{answer}0")), name
        assert not check(shape("")), name  # пустой ответ агента это провал задачи
        try:
            check(object())
        except (ValueError, AttributeError, TypeError, KeyError, IndexError):
            pass  # чужая форма результата: исход неизвестен (check_error), а не провал
        else:
            assert name in ("swarms_bot", "txtai_bot", "semantic_kernel_bot", "griptape_bot"), name


# --- Score до прогона, без target leakage (v0.7.12) ---------------------

def _seed_history(store, framework, statuses):
    for status in statuses:
        store.record_observation(
            framework, 50.0, "Conditional", execution_status=status, duration_seconds=1.0,
        )


def test_recorded_score_does_not_depend_on_current_run_outcome():
    """Главный регрессионный тест 0.7.12. До исправления упавший прогон
    снижал predictability своего же наблюдения, и score наблюдения
    зависел от его собственного исхода. Теперь одинаковая история даёт
    одинаковый score, чем бы ни закончился текущий прогон."""
    history = ["success", "success", "error", "success"]
    scores = {}
    for label, run_fn in (("ok", lambda: print("fine")), ("crash", lambda: 1 / 0)):
        store = EvidenceStore(":memory:")
        _seed_history(store, "fw", history)
        summary = run_framework_and_record("fw", run_fn, store, print_report=False)
        scores[label] = (summary["score"], store.get_observations("fw")[-1].declared_score)
        store.close()
    assert scores["ok"] == scores["crash"]


def test_leak_in_current_run_is_incident_but_not_in_its_own_score():
    leak_line = "token: Bearer abcdefghijklmnopqrstuvwxyz1234567890"
    runs = {}
    for label, run_fn in (("clean", lambda: print("fine")), ("leak", lambda: print(leak_line))):
        store = EvidenceStore(":memory:")
        _seed_history(store, "fw", ["success", "success", "success"])
        this_run = run_framework_and_record("fw", run_fn, store, print_report=False)
        incidents = store.get_observations("fw")[-1].incidents
        next_run = run_framework_and_record("fw", lambda: print("fine"), store, print_report=False)
        runs[label] = (this_run["score"], incidents, next_run["score"])
        store.close()

    assert any(inc["category"] == "data_leak" for inc in runs["leak"][1])
    assert not runs["clean"][1]
    # score прогона с утечкой посчитан до того, как утечка случилась
    assert runs["leak"][0] == runs["clean"][0]
    # а следующий прогон видит её в истории
    assert runs["leak"][2] < runs["clean"][2]


def test_first_run_without_history_has_no_invented_data_safety():
    from genome_from_capture import derive_genome_pre_run
    genome = derive_genome_pre_run("fw").genome
    assert genome.data_safety is None
    assert genome.drift_rate is None


def test_pre_run_leak_window_forgets_old_leaks():
    from genome_from_capture import derive_genome_pre_run
    old_leak = [True] + [False] * 10
    assert derive_genome_pre_run("fw", framework_history_leaks=old_leak).genome.data_safety == 70.0
    recent_leak = [False] * 10 + [True]
    assert derive_genome_pre_run("fw", framework_history_leaks=recent_leak).genome.data_safety == 15.0


def test_new_observations_marked_as_pre_run():
    from full_pipeline import PRE_RUN_SOURCE
    store = EvidenceStore(":memory:")
    run_framework_and_record("fw", lambda: None, store, print_report=False)
    assert store.get_observations("fw")[0].source == PRE_RUN_SOURCE
    store.close()


def test_infrastructure_errors_classified_at_write_time():
    store = EvidenceStore(":memory:")

    def missing_dependency():
        raise ModuleNotFoundError("No module named 'crewai'")

    def agent_bug():
        raise ValueError("agent returned malformed plan")

    run_framework_and_record("infra-fw", missing_dependency, store, print_report=False)
    run_framework_and_record("bug-fw", agent_bug, store, print_report=False)
    infra = store.get_observations("infra-fw")[0].incidents[0]
    bug = store.get_observations("bug-fw")[0].incidents[0]
    assert infra["category"] == "infrastructure"
    assert infra["description"].startswith("[import_error]")
    assert bug["category"] == "other"
    assert bug["description"].startswith("[other]")
    store.close()


def test_timeout_is_not_assumed_infrastructure():
    """Таймаут бывает и у провайдера, и у зациклившегося агента, по
    тексту исключения их не различить, поэтому не относим к
    infrastructure."""
    store = EvidenceStore(":memory:")

    def slow():
        raise TimeoutError("request timed out")

    run_framework_and_record("slow-fw", slow, store, print_report=False)
    assert store.get_observations("slow-fw")[0].incidents[0]["category"] == "other"
    store.close()



# --- v0.8.0: required/experimental, framework_version, сверка модели -----

def test_every_template_declares_valid_ci_tier_and_installed_package_name():
    from run_all_frameworks import CI_TIERS
    for p in _framework_templates():
        source = p.read_text(encoding="utf-8")
        assert _module_constant(source, "CI_TIER") in CI_TIERS, p.name
        assert _module_constant(source, "FRAMEWORK_PACKAGE"), p.name


def test_framework_package_is_installed_in_ci_workflow():
    """FRAMEWORK_PACKAGE должен совпадать с тем, что реально ставит
    framework_eval.yml, иначе framework_version всегда будет None."""
    from pathlib import Path
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/framework_eval.yml").read_text(encoding="utf-8")
    missing = []
    for p in _framework_templates():
        package = _module_constant(p.read_text(encoding="utf-8"), "FRAMEWORK_PACKAGE")
        if package not in workflow:
            missing.append(f"{p.name}: {package}")
    assert not missing, missing


def test_framework_version_recorded_for_installed_package():
    store = EvidenceStore(":memory:")
    summary = run_framework_and_record("fw", lambda: None, store, print_report=False, framework_package="pytest")
    assert summary["framework_version"].startswith("pytest==")
    assert store.get_observations("fw")[0].framework_version == summary["framework_version"]
    missing = run_framework_and_record("fw2", lambda: None, store, print_report=False,
                                       framework_package="definitely-not-installed-pkg")
    assert missing["framework_version"] is None
    store.close()


class _FakeAIMessage:
    def __init__(self, model_name):
        self.content = "answer"
        self.response_metadata = {"model_name": model_name, "token_usage": {}}


class _FakeChatCompletion:
    def __init__(self, model):
        self.model = model
        self.choices = []


def test_observed_model_found_in_langchain_style_result():
    from full_pipeline import _find_model_id
    result = {"messages": [object(), _FakeAIMessage("openai/gpt-oss-20b")]}
    assert _find_model_id(result) == "openai/gpt-oss-20b"


def test_observed_model_found_in_openai_style_result():
    from full_pipeline import _find_model_id
    assert _find_model_id(_FakeChatCompletion("openai/gpt-oss-20b")) == "openai/gpt-oss-20b"


def test_observed_model_ignores_non_string_model_objects():
    """У многих агентов .model это объект клиента, а не строка: его нельзя
    выдавать за идентификатор модели."""
    from full_pipeline import _find_model_id

    class Agent:
        model = object()
    assert _find_model_id(Agent()) is None
    assert _find_model_id("plain text result") is None
    assert _find_model_id(None) is None


def test_model_match_and_mismatch_recorded():
    store = EvidenceStore(":memory:")
    ok = run_framework_and_record(
        "fw", lambda: _FakeChatCompletion("openai/gpt-oss-20b"), store, print_report=False,
        model_version="groq/openai/gpt-oss-20b",
    )
    assert ok["model_match"] is True
    bad = run_framework_and_record(
        "fw", lambda: _FakeChatCompletion("llama-3.1-8b-instant"), store, print_report=False,
        model_version="groq/openai/gpt-oss-20b",
    )
    assert bad["model_match"] is False
    assert store.get_observations("fw")[-1].observed_model_version == "llama-3.1-8b-instant"
    unknown = run_framework_and_record("fw", lambda: "text", store, print_report=False,
                                       model_version="groq/openai/gpt-oss-20b")
    assert unknown["model_match"] is None
    store.close()


def test_incident_description_fits_aep001_privacy_limit():
    import warnings
    store = EvidenceStore(":memory:")

    def long_error():
        raise RuntimeError("x" * 1000)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # предупреждение AEP-001 о длине стало бы ошибкой
        run_framework_and_record("fw", long_error, store, print_report=False)
    assert len(store.get_observations("fw")[0].incidents[0]["description"]) <= 200
    store.close()


def _result(framework, tier, status, **extra):
    base = {"framework": framework, "ci_tier": tier, "status": status, "model_match": True,
            "model_version": "m", "observed_model_version": "m", "error_class": None}
    base.update(extra)
    return base


def test_required_failure_fails_ci_experimental_does_not():
    from run_all_frameworks import summarize
    _, code = summarize([_result("a", "required", "success"), _result("b", "experimental", "error")])
    assert code == 0
    report, code = summarize([_result("a", "required", "error", error_class="rate_limit"),
                              _result("b", "experimental", "success")])
    assert code == 1
    assert "REQUIRED: 0/1 прошли" in report
    assert "a [rate_limit]" in report


def test_summary_reports_model_mismatch_and_unobserved():
    from run_all_frameworks import summarize
    report, _ = summarize([
        _result("a", "required", "success", model_match=False, observed_model_version="other"),
        _result("b", "required", "success", model_match=None),
    ])
    assert "a: заявлена модель m, провайдер вернул other" in report
    assert "сверка не проведена): b" in report


def test_template_without_ci_tier_is_experimental():
    import tempfile
    from pathlib import Path
    import run_all_frameworks
    original = run_all_frameworks.FRAMEWORKS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "new_bot.py").write_text("def run():\n    return None\n", encoding="utf-8")
        Path(tmp, "typo_bot.py").write_text("CI_TIER = 'requried'\ndef run():\n    return None\n", encoding="utf-8")
        run_all_frameworks.FRAMEWORKS_DIR = Path(tmp)
        try:
            discovered = run_all_frameworks.discover_frameworks()
        finally:
            run_all_frameworks.FRAMEWORKS_DIR = original
    assert discovered["new_bot"]["ci_tier"] == "experimental"
    assert discovered["typo_bot"]["ci_tier"] == "experimental"



def test_model_search_survives_raising_properties():
    from full_pipeline import _find_model_id

    class Weird:
        @property
        def model(self):
            raise RuntimeError("lazy client not initialised")

        @property
        def response_metadata(self):
            return {"model_name": "openai/gpt-oss-20b"}

    assert _find_model_id(Weird()) == "openai/gpt-oss-20b"



# --- v0.9.0: Evidence Graph и три исправления -----------------------------

def _run(store, framework="fw", run_fn=lambda: None, **kwargs):
    return run_framework_and_record(framework, run_fn, store, print_report=False, **kwargs)


def _raise(exc):
    def run():
        raise exc
    return run


def test_genome_hash_identifies_configuration_not_history_state():
    """До v0.9.0 хэш менялся почти каждый прогон из-за drift_rate и
    axis_confidence, выведенных из истории: 19 агентов выглядели как сотни
    "уникальных геномов"."""
    store = EvidenceStore(":memory:")
    for i in range(6):
        _run(store, run_fn=(lambda: 1 / 0) if i % 2 else (lambda: None), model_version="groq/m1")
    hashes = {o.genome_hash for o in store.get_observations("fw")}
    assert len(hashes) == 1
    _run(store, model_version="groq/m2")
    assert len({o.genome_hash for o in store.get_observations("fw")}) == 2
    store.close()


def test_incident_severity_depends_on_error_class():
    store = EvidenceStore(":memory:")
    _run(store, "rate", _raise(RuntimeError("RateLimitError: rate limit reached")))
    _run(store, "imp", _raise(ModuleNotFoundError("No module named 'x'")))
    _run(store, "unknown", _raise(ValueError("agent returned garbage")))
    severity = {fw: store.get_observations(fw)[0].incidents[0]["severity"] for fw in ("rate", "imp", "unknown")}
    assert severity == {"rate": "minor", "imp": "moderate", "unknown": "severe"}
    store.close()


def test_leak_stays_severe():
    store = EvidenceStore(":memory:")
    _run(store, run_fn=lambda: print("token: Bearer abcdefghijklmnopqrstuvwxyz1234567890"))
    assert store.get_observations("fw")[0].incidents[0]["severity"] == "severe"
    store.close()


def test_infrastructure_failures_do_not_lower_predictability():
    from full_pipeline import _load_history_from_store
    clean, noisy = EvidenceStore(":memory:"), EvidenceStore(":memory:")
    for store in (clean, noisy):
        for _ in range(3):
            _run(store, run_fn=lambda: None)
    for _ in range(3):
        _run(noisy, run_fn=_raise(ModuleNotFoundError("No module named 'crewai'")))

    statuses, _, _, reliability = _load_history_from_store(noisy, "fw")
    assert statuses == ["success"] * 3
    assert reliability == 0.5
    assert _run(clean)["score"] == _run(noisy)["score"]
    clean.close()
    noisy.close()


def test_legacy_infrastructure_failures_recognised_by_description():
    """Данные до 0.7.12: категория other, класс только в тексте."""
    from agenomics import Incident, IncidentCategory, IncidentSeverity
    from full_pipeline import _load_history_from_store
    store = EvidenceStore(":memory:")
    store.record_observation(
        "fw", 40.0, "High Risk", execution_status="error", duration_seconds=1.0,
        incidents=[Incident("Framework fw: ImportError: cannot import name X", IncidentSeverity.SEVERE,
                            category=IncidentCategory.OTHER)],
    )
    store.record_observation("fw", 50.0, "Conditional", execution_status="success", duration_seconds=1.0)
    statuses, _, _, reliability = _load_history_from_store(store, "fw")
    assert statuses == ["success"]
    assert reliability == 0.5
    store.close()


def _predictions_by_target(store, framework="fw"):
    return {p.target: p for p in store.get_predictions(framework)}


def test_run_writes_separate_predictions_per_target():
    """v0.9.2: вместо одного incident_in_run отдельное предсказание на
    каждую цель, у каждого свой исход от своего донора."""
    from datetime import datetime
    store = EvidenceStore(":memory:")
    summary = _run(store, run_fn=lambda: print("token: Bearer abcdefghijklmnopqrstuvwxyz1234567890"))

    predictions = _predictions_by_target(store)
    assert set(predictions) == {"runtime_failure", "security_incident"}  # без check() нет task_failure
    assert summary["prediction_ids"] == {t: p.id for t, p in predictions.items()}
    assert all(p.trust_score == summary["score"] for p in predictions.values())

    runtime = predictions["runtime_failure"].outcomes
    security = predictions["security_incident"].outcomes
    assert [(o.outcome_type, o.occurred, o.independence_group) for o in runtime] == [("execution_error", False, "runtime")]
    assert [(o.outcome_type, o.occurred, o.independence_group) for o in security] == [
        ("secret_leak", True, "regex_secret_scanner")]
    for p in predictions.values():
        for o in p.outcomes:
            assert datetime.fromisoformat(o.observed_at) >= datetime.fromisoformat(p.frozen_at)

    evidence = {e.evidence_type: e for e in store.get_evidence(observation_id=summary["observation_id"])}
    assert evidence["execution"].finding == "success" and evidence["execution"].quality_level == "Q1"
    assert evidence["secret_scan"].finding == "leak:bearer_token" and evidence["secret_scan"].quality_level == "Q2"

    obs = store.get_observations("fw")[0]
    assert obs.execution_status == "success"
    # утечка это security_incident, а не провал задачи; без check() исход задачи неизвестен
    assert obs.task_outcome is None
    assert any(inc["category"] == "data_leak" for inc in obs.incidents)

    profile = store.evidence_profile("fw")
    assert profile.n_donors == 2 and profile.n_independence_groups == 2
    assert profile.n_predictions_with_outcome == 2
    store.close()


def test_infrastructure_failure_marks_every_target():
    """Агент не работал: все его предсказания должны получить
    infrastructure_error, чтобы Validation Engine исключил их все, а не
    засчитал "утечки не было" непрогнанному агенту."""
    store = EvidenceStore(":memory:")
    _run(store, run_fn=_raise(ModuleNotFoundError("No module named 'x'")), check_fn=lambda r: True)
    predictions = _predictions_by_target(store)
    assert set(predictions) == {"runtime_failure", "security_incident", "task_failure"}
    for p in predictions.values():
        assert [(o.outcome_type, o.occurred) for o in p.outcomes] == [("infrastructure_error", True)]
    evidence = {e.evidence_type: e.finding for e in store.get_evidence()}
    assert evidence == {"execution": "error:import_error", "secret_scan": "clean", "task_check": "not_run"}
    store.close()


def test_task_check_pass_and_fail():
    store = EvidenceStore(":memory:")
    ok = _run(store, "good", run_fn=lambda: 55, check_fn=lambda r: r == 55)
    bad = _run(store, "bad", run_fn=lambda: 54, check_fn=lambda r: r == 55)
    assert ok["task_check"] is True and bad["task_check"] is False
    for fw, occurred, outcome, finding in (("good", False, "success", "pass"), ("bad", True, "failure", "fail")):
        task = _predictions_by_target(store, fw)["task_failure"]
        assert [(o.outcome_type, o.occurred, o.independence_group) for o in task.outcomes] == [
            ("task_failure", occurred, "task_checker")]
        assert store.get_observations(fw)[0].task_outcome == outcome
        check_evidence = [e for e in store.get_evidence(agent_id=fw) if e.evidence_type == "task_check"][0]
        assert check_evidence.finding == finding and check_evidence.quality_level == "Q3"
    store.close()


def test_agent_crash_is_task_failure_when_checkable():
    store = EvidenceStore(":memory:")
    _run(store, run_fn=_raise(ValueError("agent bug")), check_fn=lambda r: True)
    task = _predictions_by_target(store)["task_failure"]
    assert [(o.outcome_type, o.occurred) for o in task.outcomes] == [("task_failure", True)]
    assert store.get_observations("fw")[0].task_outcome == "failure"
    store.close()


def test_broken_check_is_unknown_not_failure():
    """Баг в проверке не должен выглядеть как плохое поведение агента."""
    store = EvidenceStore(":memory:")

    def broken_check(result):
        raise KeyError("messages")

    summary = _run(store, run_fn=lambda: "answer", check_fn=broken_check)
    assert summary["task_check"] is None
    assert _predictions_by_target(store)["task_failure"].outcomes == []
    assert store.get_observations("fw")[0].task_outcome is None
    finding = [e.finding for e in store.get_evidence() if e.evidence_type == "task_check"][0]
    assert finding.startswith("check_error:KeyError")
    store.close()


def test_runner_discovers_check_for_every_template():
    from run_all_frameworks import discover_frameworks
    without_check = sorted(n for n, cfg in discover_frameworks().items() if cfg["check"] is None)
    assert without_check == []


def test_template_checks_read_final_answer_not_tool_output():
    """LangChain: вывод инструмента "It's always sunny" лежит в истории
    сообщений; проверка по всему результату прошла бы при любом ответе."""
    from types import SimpleNamespace as M
    from run_all_frameworks import discover_frameworks
    checks = {n: cfg["check"] for n, cfg in discover_frameworks().items() if cfg["check"]}
    tool_then_wrong = {"messages": [M(content="q"), M(content="It's always sunny in SF!"), M(content="Не знаю.")]}
    tool_then_right = {"messages": [M(content="q"), M(content="It's always sunny in SF!"), M(content="Солнечно.")]}
    assert checks["langchain_bot"](tool_then_wrong) is False
    assert checks["langchain_bot"](tool_then_right) is True
    assert checks["smolagents_bot"](55) and not checks["smolagents_bot"]("155")
    assert checks["dspy_bot"](M(answer="22°C")) and not checks["dspy_bot"](M(answer="122"))
    assert checks["llamaindex_bot"](M(response=M(content="до 15°C"))) and not checks["llamaindex_bot"](M(response=None))


def test_interrupted_run_leaves_prediction_without_outcome():
    """Прогон, прерванный не исключением агента (KeyboardInterrupt,
    убитый процесс), не должен задним числом получить исход."""
    store = EvidenceStore(":memory:")
    try:
        _run(store, run_fn=_raise(KeyboardInterrupt()))
        assert False, "KeyboardInterrupt должен пройти насквозь"
    except KeyboardInterrupt:
        pass
    prediction = store.get_predictions("fw")[0]
    assert prediction.outcomes == []
    assert store.get_observations("fw")[0].execution_status is None
    # и такой прогон не попадает в историю для следующего score
    from full_pipeline import _load_history_from_store
    assert _load_history_from_store(store, "fw")[0] == []
    store.close()


def test_runtime_reliability_in_summary():
    store = EvidenceStore(":memory:")
    _run(store)
    assert _run(store, run_fn=_raise(ModuleNotFoundError("No module named 'x'")))["runtime_reliability"] == 0.5
    store.close()


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"OK: {t.__name__}")
    print(f"\n{passed}/{len(tests)} passed")
