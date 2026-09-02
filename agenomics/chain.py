"""
chain.py — Chain Risk Aggregator методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.0

CompatibilityScorer оценивает агентов как "параллельных коллег" (команду).
Но часто агенты работают ЦЕПОЧКОЙ: выход агента A — вход агента B.
В этой модели риск не усредняется, а НАКАПЛИВАЕТСЯ — сбой на любом шаге
проходит дальше по цепочке. Отдельная логика, не сводимая к среднему.
"""

from dataclasses import dataclass
from typing import List, Optional

from .trust_score import AgentGenome, TrustResult, TrustScorer


@dataclass
class ChainRiskResult:
    chain_ids: List[str]
    step_scores: List[float]
    weakest_link_id: str
    weakest_link_score: float
    chain_reliability: float  # 0-100 — произведение, НЕ среднее
    label: str


class ChainRiskAggregator:
    """Считает надёжность цепочки агентов (последовательный пайплайн)."""

    def __init__(self, scorer: Optional[TrustScorer] = None):
        self._scorer = scorer or TrustScorer()

    def score_chain(self, chain: List[AgentGenome]) -> ChainRiskResult:
        if len(chain) < 2:
            raise ValueError("Цепочка должна содержать минимум 2 агента.")

        results: List[TrustResult] = [self._scorer.score(g) for g in chain]
        step_scores = [r.score for r in results]

        # Надёжность цепочки — произведение вероятностей "агент не подведёт".
        # Пример: два агента по 90/100 в команде дают Compatibility ~90,
        # но в ЦЕПОЧКЕ (A должен отработать корректно, ЗАТЕМ B) совместная
        # надёжность — 0.9 × 0.9 = 0.81 → 81, а не 90. Слабое звено и само
        # количество шагов в цепочке снижают итог сильнее, чем в команде.
        reliability = 1.0
        for s in step_scores:
            reliability *= (s / 100.0)
        chain_reliability = round(reliability * 100, 1)

        weakest_idx = min(range(len(chain)), key=lambda i: step_scores[i])

        if chain_reliability >= 85:
            label = "Trusted"
        elif chain_reliability >= 60:
            label = "Conditional"
        else:
            label = "High Risk"

        return ChainRiskResult(
            chain_ids=[g.id for g in chain],
            step_scores=step_scores,
            weakest_link_id=chain[weakest_idx].id,
            weakest_link_score=step_scores[weakest_idx],
            chain_reliability=chain_reliability,
            label=label,
        )
