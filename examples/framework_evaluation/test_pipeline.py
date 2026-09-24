"""Тесты полного пайплайна capture_log_v2 -> genome_from_capture -> EvidenceStore."""

import sys
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


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"OK: {t.__name__}")
    print(f"\n{passed}/{len(tests)} passed")
