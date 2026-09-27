# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
external.py. Внешнее подтверждение исхода (уровень Q4), v0.9.6.

Q4 означает исход, который наступил в реальном мире и зафиксирован
внешней системой: результат матча из источника данных, статус заказа во
внешней системе, решение человека-ревьюера. Внутренняя проверка
(check() шаблона, LLM-судья) это Q3, не Q4, и через этот модуль не
записывается.

Три правила, которые делают такое подтверждение независимым:

1. Верификатор получает PredictionView без Trust Score: подтверждение не
   может от него зависеть, иначе score проверял бы сам себя.
2. Время подтверждения строго позже заморозки предсказания.
3. Группа независимости донора-верификатора не совпадает с группами
   доноров, уже давших исходы этому предсказанию: внешнее подтверждение
   не может быть тем же источником.

Использование:

    class MatchResultVerifier:
        donor_id = "sports.match_results"
        def verify(self, prediction):
            result = fetch_result(prediction.task_version)   # внешний источник
            if result is None:
                return None                                  # исход ещё не наступил
            return ExternalVerification(
                occurred=result.prediction_failed, outcome_type="task_failure",
                source_type="external_system", source_reference=result.match_id,
                verification_method="api_assertion", verified_at=result.finished_at,
            )

    store.register_donor("sports.match_results", "outcome", "Match results API", "sports_results_api")
    record_external_outcome(store, prediction_id, MatchResultVerifier())

Проект: Prizolov Lab
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

from .evidence_graph import OUTCOME_CLASS_BY_TYPE


@dataclass(frozen=True)
class PredictionView:
    """То, что видит верификатор. Trust Score сюда намеренно не входит."""
    prediction_id: int
    agent_id: str
    target: str
    horizon: str
    frozen_at: str
    task_version: Optional[str] = None
    environment_id: Optional[str] = None


@dataclass(frozen=True)
class ExternalVerification:
    occurred: bool
    outcome_type: str
    source_type: str           # "external_system", "human_review", ...
    source_reference: str      # id записи во внешней системе, обязателен
    verification_method: str   # "api_assertion", "manual_review", ...
    verified_at: datetime      # время подтверждения во внешней системе


class ExternalOutcomeVerifier(Protocol):
    donor_id: str

    def verify(self, prediction: PredictionView) -> Optional[ExternalVerification]:
        """None, если исход ещё не наступил или внешняя система его не знает."""
        ...


def prediction_view(store, prediction_id: int) -> PredictionView:
    row = store._conn.execute(
        "SELECT id, agent_id, target, horizon, frozen_at, task_version, environment_id FROM predictions WHERE id = ?",
        (prediction_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"предсказание id={prediction_id} не найдено")
    return PredictionView(*row)


def record_external_outcome(store, prediction_id: int, verifier: ExternalOutcomeVerifier) -> Optional[int]:
    """Спрашивает верификатора и записывает подтверждённый исход с Q4 и
    verification="ground_truth". Возвращает id исхода или None, если
    исход ещё не наступил. Правила см. docstring модуля."""
    view = prediction_view(store, prediction_id)
    donor = store._require_donor(verifier.donor_id)
    result = verifier.verify(view)
    if result is None:
        return None
    if not result.source_reference:
        raise ValueError("source_reference обязателен: без него подтверждение нельзя перепроверить")
    verified_at = result.verified_at if result.verified_at.tzinfo else result.verified_at.replace(tzinfo=timezone.utc)
    frozen = datetime.fromisoformat(view.frozen_at)
    frozen = frozen if frozen.tzinfo else frozen.replace(tzinfo=timezone.utc)
    if verified_at <= frozen:
        raise ValueError(
            f"подтверждение ({verified_at.isoformat()}) не позже заморозки предсказания ({view.frozen_at})"
        )
    used_groups = {
        r[0] for r in store._conn.execute(
            "SELECT DISTINCT d.independence_group FROM outcomes o JOIN donors d ON d.donor_id = o.donor_id "
            "WHERE o.prediction_id = ?", (prediction_id,),
        )
    }
    if donor.independence_group in used_groups:
        raise ValueError(
            f"группа независимости {donor.independence_group!r} уже дала исход этому предсказанию: "
            f"внешнее подтверждение должно быть другим источником"
        )
    return store.record_outcome(
        prediction_id, verifier.donor_id, result.outcome_type, result.occurred,
        verification="ground_truth", observed_at=verified_at,
        details=f"source_type={result.source_type}; verification_method={result.verification_method}",
        outcome_class=OUTCOME_CLASS_BY_TYPE.get(result.outcome_type),
        quality_level="Q4", source_reference=result.source_reference,
    )
