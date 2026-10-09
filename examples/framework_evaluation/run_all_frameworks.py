# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
run_all_frameworks.py — автоматический раннер: авто-обнаружение всех
фреймворков в папке frameworks/ + прогон + запись в EvidenceStore.

Автор: доработка для интеграции с Agenomics
Проект: Prizolov Lab

Как добавить новый (15-й, 16-й...) фреймворк — БЕЗ РЕДАКТИРОВАНИЯ
этого файла:
    Создайте frameworks/my_framework.py с функцией run(), например:

        DOMAIN = "content"      # опционально, иначе "content" по умолчанию
        AUTONOMY = "advisory"   # опционально, иначе "advisory" по умолчанию

        def run():
            # ваш реальный вызов агента
            return my_agent.invoke(task)

    Всё — при следующем запуске run_all_frameworks.py он подхватится
    автоматически, без единой правки в этом файле.

Запуск вручную:
    python run_all_frameworks.py

[Unreleased] Каждый запуск делает два прохода по всем агентам: natural и
один стресс-сценарий (conditions.py, docs/specs/validation-data-acquisition-v1.md).
Условие одно на запуск для всех агентов и выбирается по номеру запуска
(GITHUB_RUN_NUMBER или AGENOMICS_RUN_NUMBER). Шаблон с run(ctx) и
answer(result) получает модель и задачу от раннера; шаблон со старым
run() без аргументов идёт только в natural со своей задачей и check().
AGENOMICS_STRESS=0 отключает стресс-проход, AGENOMICS_JUDGE=0 судью.
AGENOMICS_PACING_SECONDS (по умолчанию 3) пауза между агентами: у
бесплатного Groq лимит 8000 токенов в минуту на модель, и 19 агентов
подряд с судьёй его превышали (прогон 127, rate_limit у двух агентов).

Код выхода (v0.8.0): 1, если упал хотя бы один фреймворк с
CI_TIER = "required" в natural, иначе 0. Падения в стресс-когортах это
исходы эксперимента, а не поломка, и CI не валят. Падения experimental-фреймворков видны
в отчёте, но CI не валят. Шаблон без CI_TIER считается experimental:
новый фреймворк сначала должен доказать стабильность.

Запуск по расписанию — см. .github/workflows/framework_eval.yml
(GitHub Actions с cron) в этом же комплекте, или обычный cron:
    0 */6 * * * cd /path/to/project && python run_all_frameworks.py >> run.log 2>&1
"""

import importlib.util
import inspect
import os
import re
import sys
import time
from dataclasses import replace
from pathlib import Path

from agenomics import EvidenceStore

from conditions import natural_condition, run_number_from_env, stress_condition, with_fresh_canary
from fault_proxy import FaultProxy
from full_pipeline import record_harness_corrections, run_framework_and_record

FRAMEWORKS_DIR = Path(__file__).parent / "frameworks"
DB_PATH = Path(__file__).parent / "frameworks_evidence.db"
CI_TIERS = ("required", "experimental")


_KEY_LIKE = re.compile(r"\b(gsk_|sk-|hf_|AIza)[A-Za-z0-9_\-]{8,}")


def _short_error(text, limit: int = 200) -> str:
    """[v0.9.5] Текст ошибки для лога CI: первая строка, без похожего на
    ключ (GitHub маскирует секреты сам, это вторая линия защиты)."""
    first = str(text or "").strip().splitlines()[0] if str(text or "").strip() else ""
    return _KEY_LIKE.sub(lambda m: m.group(1) + "***", first)[:limit]


def summarize(results: list) -> tuple:
    """Итоговый отчёт и код выхода. Вынесено из main(), чтобы логику
    required/experimental можно было проверить без запуска фреймворков."""
    lines = []
    stress = [r for r in results if r.get("cohort_type", "natural") != "natural"]
    results = [r for r in results if r.get("cohort_type", "natural") == "natural"]
    for tier in CI_TIERS:
        tier_results = [r for r in results if r["ci_tier"] == tier]
        if not tier_results:
            continue
        failed = [r for r in tier_results if r["status"] == "error"]
        lines.append(f"{tier.upper()}: {len(tier_results) - len(failed)}/{len(tier_results)} прошли")
        for r in failed:
            # [v0.9.5] Причина рядом с классом: без неё "other" в логе CI
            # ничего не говорит, а текст ошибки был только в базе.
            reason = _short_error(r.get("error_summary"))
            lines.append(f"  ❌ {r['framework']} [{r.get('error_class') or 'other'}]" + (f": {reason}" if reason else ""))
    check_errors = [r for r in results if r.get("task_check_error")]
    for r in check_errors:
        lines.append(f"⚠️ {r['framework']}: проверка ответа не выполнилась (исход неизвестен): "
                     f"{_short_error(r['task_check_error'])}")
    mismatched = [r for r in results if r.get("model_match") is False]
    for r in mismatched:
        lines.append(f"⚠️ {r['framework']}: заявлена модель {r['model_version']}, "
                     f"провайдер вернул {r['observed_model_version']}")
    unobserved = [r["framework"] for r in results if r["status"] == "success" and r.get("model_match") is None]
    if unobserved:
        lines.append(f"Модель в ответе не найдена (сверка не проведена): {', '.join(unobserved)}")
    if stress:
        cohort = stress[0]["cohort_type"]
        from full_pipeline import _INFRASTRUCTURE_ERROR_CLASSES
        # Сбой окружения (rate limit и т. п.) не событие: такой прогон
        # исключается и в знаменатель не входит. Прогон с несколькими
        # событиями (канарейка и неверный ответ) считается один раз.
        counted = [r for r in stress if not (r["status"] == "error"
                                             and r.get("error_class") in _INFRASTRUCTURE_ERROR_CLASSES)]
        excluded = len(stress) - len(counted)
        events = []
        for r in counted:
            found = []
            if r["status"] == "error":
                found.append(f"упал [{r.get('error_class') or 'other'}]")
            if r.get("canary_disclosed"):
                found.append("раскрыл канарейку")
            if r.get("task_check") is False:
                found.append("неверный ответ")
            if found:
                events.append(f"{r['framework']} {', '.join(found)}")
        lines.append(f"Стресс ({cohort}, {stress[0].get('task_version')}): прогонов с событием {len(events)} из {len(counted)}"
                     + (f" (сбоев окружения исключено: {excluded})" if excluded else "")
                     + (": " + "; ".join(events) if events else ""))
    judged = [r for r in results + stress if r.get("judge_model")]
    if judged:
        disagree = [r["framework"] for r in judged
                    if r.get("judge_correct") is not None and r.get("task_check") is not None
                    and r["judge_correct"] != r["task_check"]]
        errors = [r["judge_error"] for r in judged if r.get("judge_error")]
        lines.append(f"Судья: оценил {sum(r.get('judge_correct') is not None for r in judged)} из {len(judged)}"
                     + (f", расходится с проверкой: {', '.join(disagree)}" if disagree else "")
                     + (f"; без оценки {len(errors)}, например: {_short_error(errors[0])}" if errors else ""))
    required_failed = [r for r in results if r["ci_tier"] == "required" and r["status"] == "error"]
    return "\n".join(lines), (1 if required_failed else 0)


def _accepts_argument(fn) -> bool:
    try:
        return len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        return False


def discover_frameworks(include_disabled: bool = False) -> dict:
    """
    Сканирует frameworks/*.py, импортирует каждый файл как модуль и
    берёт из него функцию run() (обязательна) + DOMAIN/AUTONOMY/
    MODEL_VERSION/PROMPT_VERSION (опциональны для раннера; MODEL_VERSION
    обязателен для шаблонов в этой папке, это проверяет test_pipeline.py),
    FRAMEWORK_PACKAGE и CI_TIER. Файлы без run() пропускаются с предупреждением,
    а не роняют весь скрипт — тот же принцип отказоустойчивости,
    что и в capture_log_v2.py.

    [v0.9.5] DISABLED = "<причина>" в шаблоне выключает его: прогоны не
    запускаются, а файл и накопленная история остаются. Выключаются
    шаблоны, которые не дают данных об агенте (нет ключа, не ставится
    библиотека, внешний баг): их прогоны целиком уходят в
    infrastructure_error и только тратят лимит провайдера. По умолчанию
    выключенные не возвращаются; include_disabled=True нужен для отчёта.
    """
    discovered = {}
    if not FRAMEWORKS_DIR.exists():
        print(f"[WARN] Папка {FRAMEWORKS_DIR} не найдена — нечего запускать.")
        return discovered

    for py_file in sorted(FRAMEWORKS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue  # файлы вида _helpers.py не считаются фреймворками
        name = py_file.stem
        try:
            spec = importlib.util.spec_from_file_location(name, py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"[WARN] Не удалось загрузить {py_file.name}: {e} — пропущен, остальные не пострадали.")
            continue

        if not hasattr(module, "run"):
            print(f"[WARN] {py_file.name} не содержит функцию run() — пропущен.")
            continue

        discovered[name] = {
            "disabled": getattr(module, "DISABLED", None),
            "run": module.run,
            "domain": getattr(module, "DOMAIN", "content"),
            "autonomy": getattr(module, "AUTONOMY", "advisory"),
            "model_version": getattr(module, "MODEL_VERSION", None),
            "prompt_version": getattr(module, "PROMPT_VERSION", None),
            "framework_package": getattr(module, "FRAMEWORK_PACKAGE", None),
            "ci_tier": getattr(module, "CI_TIER", "experimental"),
            "check": getattr(module, "check", None),
            "answer": getattr(module, "answer", None),
            # [Unreleased] run(ctx): шаблон принимает условие от раннера
            "takes_context": _accepts_argument(module.run) and hasattr(module, "answer"),
        }
        if discovered[name]["ci_tier"] not in CI_TIERS:
            print(f"[WARN] {py_file.name}: CI_TIER={discovered[name]['ci_tier']!r} "
                  f"не из {CI_TIERS}, считается experimental.")
            discovered[name]["ci_tier"] = "experimental"
    if include_disabled:
        return discovered
    return {name: config for name, config in discovered.items() if not config["disabled"]}


def main():
    everything = discover_frameworks(include_disabled=True)
    frameworks = {name: config for name, config in everything.items() if not config["disabled"]}
    if not frameworks:
        print("Фреймворков не найдено. Добавьте .py файлы с функцией run() в папку frameworks/.")
        return 1

    print(f"Обнаружено фреймворков: {len(frameworks)} — {list(frameworks.keys())}")
    for name, config in everything.items():
        if config["disabled"]:
            print(f"  выключен: {name} — {config['disabled']}")
    print()

    store = EvidenceStore(str(DB_PATH))
    corrected = record_harness_corrections(store)
    if corrected:
        print(f"Поправка: {corrected} предсказаний прогонов, упавших из-за обвязки (harness_error), исключены")
    run_number = run_number_from_env(default=len(store.get_observations()) // max(len(frameworks), 1))
    passes = [natural_condition(run_number)]
    if os.environ.get("AGENOMICS_STRESS", "1") != "0":
        passes.append(stress_condition(run_number))
    judge_fn = None
    if os.environ.get("AGENOMICS_JUDGE", "1") != "0" and os.environ.get("GROQ_API_KEY"):
        from judge import judge_answer
        judge_fn = judge_answer
    print(f"Запуск {run_number}: " + "; ".join(f"{c.cohort_type} {c.model} {c.task_version}" for c in passes))
    print()

    results = []
    for condition in passes:
        proxy = FaultProxy() if condition.fault else None
        if proxy is not None:
            proxy.__enter__()
        try:
            pacing = float(os.environ.get("AGENOMICS_PACING_SECONDS", "3"))
            for index, (name, config) in enumerate(frameworks.items()):
                if index and pacing > 0:
                    time.sleep(pacing)
                if config["takes_context"]:
                    ctx = with_fresh_canary(replace(condition))
                elif condition.cohort_type == "natural":
                    ctx = None  # старый шаблон: своя задача и check()
                else:
                    continue    # в стресс-когорты идут только шаблоны с run(ctx)
                summary = run_framework_and_record(
                    name, config["run"], store,
                    domain=config["domain"], autonomy=config["autonomy"],
                    model_version=config["model_version"], prompt_version=config["prompt_version"],
                    framework_package=config["framework_package"],
                    check_fn=config["check"],
                    print_report=False,
                    ctx=ctx, answer_fn=config["answer"], proxy=proxy, judge_fn=judge_fn,
                )
                summary["ci_tier"] = config["ci_tier"]
                summary["model_version"] = ctx.model_version if ctx is not None else config["model_version"]
                results.append(summary)
                marker = "✅" if summary["status"] == "success" else "❌"
                leak_marker = " ⚠️ УТЕЧКА" if summary["leaked_secrets"] else ""
                canary_marker = " ⚠️ КАНАРЕЙКА" if summary.get("canary_disclosed") else ""
                task_marker = {True: " задача✅", False: " задача❌", None: ""}[summary["task_check"]]
                judge_marker = {True: " судья✅", False: " судья❌", None: ""}[summary.get("judge_correct")]
                reliability = summary["runtime_reliability"]
                # Trust Score и надёжность запуска разные величины (v0.9.0): score не
                # учитывает падения из-за окружения, надёжность учитывает всё.
                print(f"{marker} [{summary['cohort_type']}] {name:22s} score={summary['score']:.1f} ({summary['label']}) "
                      f"reliability={'—' if reliability is None else f'{reliability:.0%}'}"
                      f"{task_marker}{judge_marker}{leak_marker}{canary_marker}"
                      + (f" [{summary['error_class']}]" if summary["status"] == "error" else ""))
        finally:
            if proxy is not None:
                proxy.__exit__(None, None, None)
        print()

    store.close()

    natural = [r for r in results if r["cohort_type"] == "natural"]
    failed = [r for r in natural if r["status"] == "error"]
    leaked = [r for r in natural if r["leaked_secrets"]]
    print(f"Итого natural: {len(natural)} фреймворков, {len(failed)} упало, {len(leaked)} с находками утечек; "
          f"всего прогонов {len(results)}")
    print(f"Данные сохранены в {DB_PATH} — переживут следующий запуск (накопление истории)")

    report, exit_code = summarize(results)
    print()
    print(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
