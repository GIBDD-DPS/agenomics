"""
reports.py — форматированные Markdown-отчёты методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.0

Оборачивает TrustResult/TeamCompatibilityResult в готовый к показу
клиенту Markdown-отчёт вместо сырого dataclass.
"""

from .compatibility import TeamCompatibilityResult
from .trust_score import TrustResult


def trust_report(result: TrustResult, agent_id: str = "agent") -> str:
    lines = [
        f"## Trust Score: {agent_id}",
        "",
        f"**Score:** {result.score}/100 → **{result.label}**",
        f"**Confidence:** {result.confidence} ({result.confidence_ratio * 100:.0f}% данных)",
        "",
        "### Разбивка по осям",
    ]
    for axis, value in result.breakdown.items():
        flag = " ⚠️ insufficient data" if axis in result.insufficient_axes else ""
        lines.append(f"- {axis}: {value:.0f}/100{flag}")

    if result.capped_reason:
        lines += ["", f"⚠️ **Потолок применён:** {result.capped_reason}"]

    if result.recommendations:
        lines += ["", "### Рекомендации"]
        for i, rec in enumerate(result.recommendations, 1):
            lines.append(f"{i}. {rec}")

    lines += ["", f"_{result.attribution}_"]
    return "\n".join(lines)


def compatibility_report(result: TeamCompatibilityResult) -> str:
    lines = [
        "## Compatibility Score команды",
        "",
        f"**Средняя совместимость:** {result.average_score}/100",
        (
            f"**Самое слабое звено:** {result.weakest_pair.agent_a} ↔ "
            f"{result.weakest_pair.agent_b} ({result.weakest_pair.score}/100)"
        ),
        "",
        "### Все пары",
    ]
    for p in result.pairs:
        role_note = " (роли учтены)" if p.complementary_roles else ""
        lines.append(f"- {p.agent_a} ↔ {p.agent_b}: {p.score}/100{role_note}")
        if p.capped_reason:
            lines.append(f"  ⚠️ {p.capped_reason}")

    attribution = result.pairs[0].attribution if result.pairs else ""
    lines += ["", f"_{attribution}_"]
    return "\n".join(lines)
