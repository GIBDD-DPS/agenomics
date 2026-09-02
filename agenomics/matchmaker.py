"""
matchmaker.py — Genome Matchmaker методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.4.0

Дан список кандидатов-агентов и список нужных ролей — подбирает
назначение с максимальным средним Compatibility Score команды.
Полный перебор — годится для небольших команд (до 8 кандидатов);
для больших нужен более умный алгоритм (вне охвата текущей версии).
"""

from dataclasses import dataclass
from itertools import permutations
from typing import Dict, List, Optional

from .compatibility import CompatibilityScorer, TeamCompatibilityResult
from .trust_score import AgentGenome

_MAX_CANDIDATES_FULL_SEARCH = 8


@dataclass
class MatchResult:
    assignment: Dict[str, str]  # role -> agent_id
    team_result: TeamCompatibilityResult


class GenomeMatchmaker:
    """Подбирает оптимальное назначение ролей для команды агентов."""

    def __init__(self, scorer: Optional[CompatibilityScorer] = None):
        self._scorer = scorer or CompatibilityScorer()

    def best_team(self, candidates: List[AgentGenome], roles: List[str]) -> MatchResult:
        if len(roles) < 2:
            raise ValueError("Нужно минимум 2 роли для подбора команды.")
        if len(roles) > len(candidates):
            raise ValueError("Ролей больше, чем кандидатов — подбор невозможен.")
        if len(candidates) > _MAX_CANDIDATES_FULL_SEARCH:
            raise ValueError(
                f"Полный перебор поддерживает до {_MAX_CANDIDATES_FULL_SEARCH} "
                f"кандидатов, получено {len(candidates)}. Уменьшите список."
            )

        best: Optional[MatchResult] = None

        for combo in permutations(candidates, len(roles)):
            assigned = []
            for agent, role in zip(combo, roles):
                # Копия генома с назначенной ролью — не мутируем исходный вход.
                fields = dict(agent.__dict__)
                fields["role"] = role
                assigned.append(AgentGenome(**fields))

            team_result = self._scorer.score_team(assigned)

            if best is None or team_result.average_score > best.team_result.average_score:
                best = MatchResult(
                    assignment={role: a.id for role, a in zip(roles, assigned)},
                    team_result=team_result,
                )

        return best
