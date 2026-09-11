"""
classify_failures.py. Классифицирует причины падения фреймворков по
уже сохранённому тексту инцидента (Incident.description), без
изменения схемы EvidenceStore и без новой инструментации.

Проект: Prizolov Lab

Работает на любой уже существующей базе, включая исторические данные,
накопленные до появления этого скрипта. Честная оговорка: наблюдения,
записанные до v0.7.4 (когда full_pipeline.py начал сохранять реальный
текст исключения, а не шаблонную фразу), классифицируются как "other" -
не потому что причина неизвестна, а потому что деталей для
классификации в самой записи никогда не было. Со временем, по мере
накопления новых наблюдений, доля "other" должна снижаться сама.
"""

import re
import sqlite3
from collections import Counter, defaultdict

_PATTERNS = [
    ("rate_limit", re.compile(r"RateLimitError|rate limit", re.IGNORECASE)),
    ("import_error", re.compile(r"ImportError|ModuleNotFoundError")),
    ("model_unavailable", re.compile(r"does not exist or you do not have access|model_not_found", re.IGNORECASE)),
    ("auth_error", re.compile(r"No API key|api key was provided|authentication", re.IGNORECASE)),
    ("provider_routing_error", re.compile(r"auto-router|Cannot select", re.IGNORECASE)),
    ("known_upstream_bug", re.compile(r"cache_breakpoint")),
    ("timeout", re.compile(r"[Tt]imeout|TimeoutError")),
]


def classify_error(description: str) -> str:
    """Возвращает одну категорию по первому совпавшему паттерну.
    'other', если ни один паттерн не подошёл, не 'unknown' - явно
    отличаем 'мы не распознали' от 'категории вообще нет'."""
    if not description:
        return "other"
    for label, pattern in _PATTERNS:
        if pattern.search(description):
            return label
    return "other"


def build_failure_report(db_path: str) -> dict:
    """Возвращает {agent_id: Counter({категория: количество})} по всем
    инцидентам в базе. Не меняет саму базу, только читает."""
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT o.agent_id, i.description FROM incidents i "
        "JOIN observations o ON i.observation_id = o.id"
    )
    report = defaultdict(Counter)
    for agent_id, description in cur.fetchall():
        category = classify_error(description)
        report[agent_id][category] += 1
    conn.close()
    return dict(report)


def print_report(db_path: str) -> None:
    report = build_failure_report(db_path)
    all_categories = sorted({cat for counts in report.values() for cat in counts})

    print(f"{'agent_id':30s} " + " ".join(f"{c:20s}" for c in all_categories))
    for agent_id in sorted(report):
        counts = report[agent_id]
        row = " ".join(f"{counts.get(c, 0):20d}" for c in all_categories)
        print(f"{agent_id:30s} {row}")

    print()
    totals = Counter()
    for counts in report.values():
        totals.update(counts)
    print("Итого по всем фреймворкам:")
    for category, count in totals.most_common():
        print(f"  {category:25s} {count}")


if __name__ == "__main__":
    import sys
    print_report(sys.argv[1] if len(sys.argv) > 1 else "frameworks_evidence.db")
