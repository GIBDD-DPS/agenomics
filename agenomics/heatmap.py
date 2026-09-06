"""
heatmap.py. Team Compatibility Heatmap.

Автор: Dm.Andreyanov
Проект: Prizolov Lab

Не новая модель, а визуализация уже существующих данных. CompatibilityScorer
(compatibility.py) уже умеет считать совместимость команды из 3+ агентов
через score_team(); этот модуль превращает результат в матрицу для
визуализации (heatmap), а также, опционально, в готовое SVG-изображение.

Рендер SVG сделан вручную (без внешних библиотек вроде matplotlib).
Тот же принцип "ядро без внешних зависимостей", что и во всём agenomics.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from .compatibility import CompatibilityScorer, TeamCompatibilityResult
from .trust_score import AgentGenome

_HEATMAP_COLORS = [
    (0, "#C62828"),    # 0, сильный конфликт
    (50, "#E65100"),   # 50, потолок этического конфликта
    (70, "#F9A825"),   # 70
    (85, "#7CB342"),   # 85
    (100, "#2E7D32"),  # 100, полная совместимость
]


@dataclass
class CompatibilityMatrix:
    agent_ids: List[str]
    matrix: List[List[Optional[float]]]  # matrix[i][j] = score(agent_i, agent_j), None по диагонали
    average_score: float
    weakest_pair: tuple  # (agent_a_id, agent_b_id, score)


def build_compatibility_matrix(agents: List[AgentGenome], scorer: Optional[CompatibilityScorer] = None) -> CompatibilityMatrix:
    """Строит полную N×N матрицу совместимости команды. Переиспользует
    CompatibilityScorer.score_team(), не отдельную логику подсчёта."""
    if len(agents) < 2:
        raise ValueError("Нужно минимум 2 агента для матрицы совместимости.")

    scorer = scorer or CompatibilityScorer()
    team_result: TeamCompatibilityResult = scorer.score_team(agents)

    ids = [a.id for a in agents]
    index = {agent_id: i for i, agent_id in enumerate(ids)}
    n = len(ids)
    matrix: List[List[Optional[float]]] = [[None] * n for _ in range(n)]

    for pair in team_result.pairs:
        i, j = index[pair.agent_a], index[pair.agent_b]
        matrix[i][j] = pair.score
        matrix[j][i] = pair.score  # симметрично

    weakest = team_result.weakest_pair
    return CompatibilityMatrix(
        agent_ids=ids,
        matrix=matrix,
        average_score=team_result.average_score,
        weakest_pair=(weakest.agent_a, weakest.agent_b, weakest.score),
    )


def _color_for_score(score: float) -> str:
    for threshold, color in _HEATMAP_COLORS:
        if score <= threshold:
            return color
    return _HEATMAP_COLORS[-1][1]


def render_heatmap_svg(matrix: CompatibilityMatrix, cell_size: int = 70) -> str:
    """Рендерит матрицу совместимости в SVG (текст, готовый сохранить как
    .svg или вставить в HTML). Без внешних зависимостей для рисования."""
    n = len(matrix.agent_ids)
    label_width = 140
    width = label_width + n * cell_size + 20
    height = label_width + n * cell_size + 20

    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#0F1930"/>',
    ]

    # Подписи сверху (повёрнутые) и слева
    for i, agent_id in enumerate(matrix.agent_ids):
        x = label_width + i * cell_size + cell_size / 2
        y = label_width - 10
        svg_parts.append(
            f'<text x="{x}" y="{y}" fill="#C7D2E8" font-size="12" text-anchor="start" '
            f'transform="rotate(-45 {x} {y})">{agent_id}</text>'
        )
        y_row = label_width + i * cell_size + cell_size / 2 + 4
        svg_parts.append(f'<text x="{label_width - 10}" y="{y_row}" fill="#C7D2E8" font-size="12" text-anchor="end">{agent_id}</text>')

    # Ячейки
    for i in range(n):
        for j in range(n):
            x = label_width + j * cell_size
            y = label_width + i * cell_size
            score = matrix.matrix[i][j]
            if i == j or score is None:
                fill = "#1B2A4A"
                text = "-"
            else:
                fill = _color_for_score(score)
                text = f"{score:.0f}"
            svg_parts.append(f'<rect x="{x}" y="{y}" width="{cell_size - 4}" height="{cell_size - 4}" fill="{fill}" rx="6"/>')
            svg_parts.append(
                f'<text x="{x + (cell_size - 4) / 2}" y="{y + (cell_size - 4) / 2 + 5}" '
                f'fill="white" font-size="16" font-weight="bold" text-anchor="middle">{text}</text>'
            )

    svg_parts.append("</svg>")
    return "".join(svg_parts)
