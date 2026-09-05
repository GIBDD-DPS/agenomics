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


def discover_frameworks() -> dict:
    """
    Сканирует frameworks/*.py, импортирует каждый файл как модуль и
    берёт из него функцию run() (обязательна) + DOMAIN/AUTONOMY
    (опциональны). Файлы без run() пропускаются с предупреждением,
    а не роняют весь скрипт — тот же принцип отказоустойчивости,
    что и в capture_log_v2.py.
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
            "run": module.run,
            "domain": getattr(module, "DOMAIN", "content"),
            "autonomy": getattr(module, "AUTONOMY", "advisory"),
        }
    return discovered


def main():
    frameworks = discover_frameworks()
    if not frameworks:
        print("Фреймворков не найдено. Добавьте .py файлы с функцией run() в папку frameworks/.")
        return 1

    print(f"Обнаружено фреймворков: {len(frameworks)} — {list(frameworks.keys())}")
    print()

    store = EvidenceStore(str(DB_PATH))
    results = []
    for name, config in frameworks.items():
        summary = run_framework_and_record(
            name, config["run"], store,
            domain=config["domain"], autonomy=config["autonomy"],
            print_report=False,
        )
        results.append(summary)
        marker = "✅" if summary["status"] == "success" else "❌"
        leak_marker = " ⚠️ УТЕЧКА" if summary["leaked_secrets"] else ""
        print(f"{marker} {name:20s} score={summary['score']:.1f} ({summary['label']}){leak_marker}")

    store.close()

    print()
    failed = [r for r in results if r["status"] == "error"]
    leaked = [r for r in results if r["leaked_secrets"]]
    print(f"Итого: {len(results)} фреймворков, {len(failed)} упало, {len(leaked)} с находками утечек")
    print(f"Данные сохранены в {DB_PATH} — переживут следующий запуск (накопление истории)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
