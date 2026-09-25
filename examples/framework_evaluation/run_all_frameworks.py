# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
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

Код выхода (v0.8.0): 1, если упал хотя бы один фреймворк с
CI_TIER = "required", иначе 0. Падения experimental-фреймворков видны
в отчёте, но CI не валят. Шаблон без CI_TIER считается experimental:
новый фреймворк сначала должен доказать стабильность.

Запуск по расписанию — см. .github/workflows/framework_eval.yml
(GitHub Actions с cron) в этом же комплекте, или обычный cron:
    0 */6 * * * cd /path/to/project && python run_all_frameworks.py >> run.log 2>&1
"""

import importlib.util
import sys
from pathlib import Path

from agenomics import EvidenceStore

from full_pipeline import run_framework_and_record

FRAMEWORKS_DIR = Path(__file__).parent / "frameworks"
DB_PATH = Path(__file__).parent / "frameworks_evidence.db"
CI_TIERS = ("required", "experimental")


def summarize(results: list) -> tuple:
    """Итоговый отчёт и код выхода. Вынесено из main(), чтобы логику
    required/experimental можно было проверить без запуска фреймворков."""
    lines = []
    for tier in CI_TIERS:
        tier_results = [r for r in results if r["ci_tier"] == tier]
        if not tier_results:
            continue
        failed = [r for r in tier_results if r["status"] == "error"]
        lines.append(f"{tier.upper()}: {len(tier_results) - len(failed)}/{len(tier_results)} прошли")
        for r in failed:
            lines.append(f"  ❌ {r['framework']} [{r.get('error_class') or 'other'}]")
    mismatched = [r for r in results if r.get("model_match") is False]
    for r in mismatched:
        lines.append(f"⚠️ {r['framework']}: заявлена модель {r['model_version']}, "
                     f"провайдер вернул {r['observed_model_version']}")
    unobserved = [r["framework"] for r in results if r["status"] == "success" and r.get("model_match") is None]
    if unobserved:
        lines.append(f"Модель в ответе не найдена (сверка не проведена): {', '.join(unobserved)}")
    required_failed = [r for r in results if r["ci_tier"] == "required" and r["status"] == "error"]
    return "\n".join(lines), (1 if required_failed else 0)


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
    results = []
    for name, config in frameworks.items():
        summary = run_framework_and_record(
            name, config["run"], store,
            domain=config["domain"], autonomy=config["autonomy"],
            model_version=config["model_version"], prompt_version=config["prompt_version"],
            framework_package=config["framework_package"],
            check_fn=config["check"],
            print_report=False,
        )
        summary["ci_tier"] = config["ci_tier"]
        summary["model_version"] = config["model_version"]
        results.append(summary)
        marker = "✅" if summary["status"] == "success" else "❌"
        leak_marker = " ⚠️ УТЕЧКА" if summary["leaked_secrets"] else ""
        task_marker = {True: " задача✅", False: " задача❌", None: ""}[summary["task_check"]]
        # Trust Score и надёжность запуска разные величины (v0.9.0): score не
        # учитывает падения из-за окружения, надёжность учитывает всё.
        print(f"{marker} {name:22s} score={summary['score']:.1f} ({summary['label']}) "
              f"reliability={summary['runtime_reliability']:.0%}{task_marker}{leak_marker}")

    store.close()

    print()
    failed = [r for r in results if r["status"] == "error"]
    leaked = [r for r in results if r["leaked_secrets"]]
    print(f"Итого: {len(results)} фреймворков, {len(failed)} упало, {len(leaked)} с находками утечек")
    print(f"Данные сохранены в {DB_PATH} — переживут следующий запуск (накопление истории)")

    report, exit_code = summarize(results)
    print()
    print(report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
