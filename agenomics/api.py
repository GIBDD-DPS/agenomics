"""
api.py — минимальный веб-API методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.1.0

Оборачивает уже протестированный TrustScorer (см. trust_score.py и
tests/test_trust_score.py) в HTTP-эндпоинт. Используется amvera.yml
для деплоя (см. run.command: uvicorn agenomics.api:app ...).

Локальный запуск для проверки:
    uvicorn agenomics.api:app --reload --port 8000

Пример запроса:
    curl -X POST http://localhost:8000/score \
      -H "Content-Type: application/json" \
      -d '{
            "id": "cashflow-predictor",
            "domain": "finance",
            "autonomy": "autonomous",
            "transparency": 75,
            "bias_control": 80,
            "data_safety": 85,
            "drift_rate": 0.1,
            "has_ledger": false
          }'
"""

from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .trust_score import AgentGenome, Autonomy, ImpactTier, TrustScorer

app = FastAPI(
    title="Agenomics API",
    description=(
        "Genetics for AI Agents — Trust Score calculator для автономных "
        "ИИ-агентов. Методология: см. docs/METHODOLOGY.md в репозитории."
    ),
    version="0.1.0",
)

_scorer = TrustScorer()


class GenomeRequest(BaseModel):
    id: str = Field(..., description="Уникальный идентификатор агента")
    domain: Optional[str] = Field(
        None, description="Домен агента, напр. 'finance', 'support', 'content'"
    )
    autonomy: str = Field(
        "advisory", description="'advisory' (только советует) или 'autonomous' (действует сам)"
    )
    transparency: Optional[float] = Field(None, ge=0, le=100)
    bias_control: Optional[float] = Field(None, ge=0, le=100)
    data_safety: Optional[float] = Field(None, ge=0, le=100)
    drift_rate: Optional[float] = Field(
        None, ge=0, le=1, description="Доля дрейфа поведения агента, 0.0-1.0"
    )
    has_ledger: bool = Field(False, description="Есть ли журнал аудита (Genome Ledger)")
    accountability_override: Optional[float] = Field(
        None, ge=0, le=100, description="Ручная оценка Accountability, если есть точнее данные"
    )
    tier_override: Optional[int] = Field(
        None, ge=1, le=3, description="Принудительный Impact Tier (1/2/3), если авто-классификация неверна"
    )


class TrustScoreResponse(BaseModel):
    id: str
    tier: int
    autonomy: str
    score: float
    label: str
    breakdown: Dict[str, float]
    insufficient_axes: List[str]
    capped_reason: Optional[str] = None
    recommendations: List[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "agenomics-api", "version": "0.1.0"}


@app.get("/")
def root() -> dict:
    return {
        "name": "Agenomics API",
        "description": "Genetics for AI Agents — Trust Score methodology.",
        "endpoints": {
            "POST /score": "Рассчитать Trust Score для генома агента",
            "GET /health": "Проверка работоспособности",
        },
        "docs": "/docs",
    }


@app.post("/score", response_model=TrustScoreResponse)
def score_agent(payload: GenomeRequest) -> TrustScoreResponse:
    try:
        autonomy = Autonomy(payload.autonomy)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"autonomy должен быть 'advisory' или 'autonomous', "
                f"получено: '{payload.autonomy}'"
            ),
        )

    tier_override = ImpactTier(payload.tier_override) if payload.tier_override else None

    genome = AgentGenome(
        id=payload.id,
        domain=payload.domain,
        autonomy=autonomy,
        transparency=payload.transparency,
        bias_control=payload.bias_control,
        data_safety=payload.data_safety,
        drift_rate=payload.drift_rate,
        has_ledger=payload.has_ledger,
        accountability_override=payload.accountability_override,
        tier_override=tier_override,
    )

    result = _scorer.score(genome)

    return TrustScoreResponse(
        id=payload.id,
        tier=int(genome.tier.value),
        autonomy=autonomy.value,
        score=result.score,
        label=result.label,
        breakdown=result.breakdown,
        insufficient_axes=result.insufficient_axes,
        capped_reason=result.capped_reason,
        recommendations=result.recommendations,
    )
