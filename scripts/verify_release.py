#!/usr/bin/env python3
"""
verify_release.py. Проверяет, что все файлы, которые должны быть в
репозитории, реально на месте, прежде чем публиковать релиз или тег.

Это не выдуманная предосторожность. За время разработки минимум 4 раза
файлы, реально построенные и протестированные, не сохранялись при
загрузке на GitHub (docs/AEP-001.md, docs/PRIZOLOV_BRIDGE_INTERFACE.md,
agenomics/per_axis_drift.py, agenomics/heatmap.py, agenomics/feedback.py,
8 из 14 шаблонов framework_evaluation) и обнаруживалось это только
через несколько версий, при реальном деплое или внешнем разборе.

Запуск: python scripts/verify_release.py
Возвращает ненулевой код выхода, если чего-то не хватает, пригоден
для pre-commit hook или шага CI перед публикацией.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Список специально не автогенерируется из CHANGELOG: файлы, которые
# реально терялись, все были в этом списке "критичных", а не в общем
# потоке. Обновляйте вручную при добавлении новых важных файлов.
CRITICAL_FILES = [
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "pyproject.toml",
    "requirements.txt",
    "amvera.yml",
    "agenomics/__init__.py",
    "agenomics/trust_score.py",
    "agenomics/compatibility.py",
    "agenomics/phenotype.py",
    "agenomics/drift.py",
    "agenomics/per_axis_drift.py",
    "agenomics/feedback.py",
    "agenomics/ledger.py",
    "agenomics/matchmaker.py",
    "agenomics/chain.py",
    "agenomics/heatmap.py",
    "agenomics/extractor.py",
    "agenomics/evaluation.py",
    "agenomics/evidence.py",
    "agenomics/hooks.py",
    "agenomics/cli.py",
    "agenomics/reports.py",
    "agenomics/api.py",
    "docs/SPECIFICATION.md",
    "docs/METHODOLOGY.md",
    "docs/AEP-001.md",
    "docs/CONNECT_YOUR_AGENTS.md",
    "docs/PRIZOLOV_BRIDGE_INTERFACE.md",
    "benchmark/README.md",
    "benchmark/BENCHMARKS.md",
    "examples/framework_evaluation/README.md",
    "examples/framework_evaluation/capture_log_v2.py",
    "examples/framework_evaluation/genome_from_capture.py",
    "examples/framework_evaluation/full_pipeline.py",
    "examples/framework_evaluation/run_all_frameworks.py",
    ".github/workflows/tests.yml",
    ".github/workflows/framework_eval.yml",
]

# 15 активных шаблонов фреймворков, добавлены отдельным списком, потому
# что именно они терялись чаще всего (8 из 14 в одном раунде).
FRAMEWORK_TEMPLATES = [
    "langchain_bot.py", "autogen_bot.py", "crewai_bot.py", "llamaindex_bot.py",
    "langgraph_bot.py", "haystack_bot.py", "camel_bot.py", "griptape_bot.py",
    "agno_bot.py", "pydantic_ai_bot.py", "dspy_bot.py", "atomic_agents_bot.py",
    "smolagents_bot.py", "google_adk_bot.py", "txtai_bot.py",
]


def main() -> int:
    missing = []

    for rel_path in CRITICAL_FILES:
        if not (REPO_ROOT / rel_path).exists():
            missing.append(rel_path)

    for template in FRAMEWORK_TEMPLATES:
        rel_path = f"examples/framework_evaluation/frameworks/{template}"
        if not (REPO_ROOT / rel_path).exists():
            missing.append(rel_path)

    if missing:
        print(f"ОТСУТСТВУЮТ {len(missing)} файлов, которые должны быть в репозитории:")
        for path in missing:
            print(f"  - {path}")
        print()
        print("Это именно тот класс проблемы, который уже случался минимум "
              "4 раза: файл был построен и протестирован, но не сохранился "
              "при загрузке. Проверьте и загрузите недостающие файлы перед "
              "публикацией релиза.")
        return 1

    print(f"Все {len(CRITICAL_FILES) + len(FRAMEWORK_TEMPLATES)} критичных файлов на месте.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
