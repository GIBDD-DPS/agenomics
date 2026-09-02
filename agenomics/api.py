"""
api.py — минимальный веб-API методологии Agenomics.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.3.0

Оборачивает уже протестированные TrustScorer и CompatibilityScorer
(см. trust_score.py, compatibility.py и соответствующие тесты) в
HTTP-эндпоинты. Используется amvera.yml для деплоя
(см. run.command: uvicorn agenomics.api:app ...).

Локальный запуск для проверки:
    uvicorn agenomics.api:app --reload --port 8000

Пример запроса /score (с профилем весов и множественным domain):
    curl -X POST http://localhost:8000/score \
      -H "Content-Type: application/json" \
      -d '{
            "id": "cashflow-predictor",
            "domains": ["support", "finance"],
            "autonomy": "autonomous",
            "transparency": 75,
            "bias_control": 80,
            "data_safety": 85,
            "drift_rate": 0.1,
            "has_ledger": false,
            "weight_profile": "finance"
          }'

Пример запроса /compatibility (2+ агента, с ролями):
    curl -X POST http://localhost:8000/compatibility \
      -H "Content-Type: application/json" \
      -d '{
            "agents": [
              {"id": "reviewer", "role": "reviewer", "bias_control": 85, "risk_tolerance": 10, "social_style": 50},
              {"id": "executor", "role": "executor", "bias_control": 85, "risk_tolerance": 90, "social_style": 50}
            ]
          }'
"""

from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .compatibility import CompatibilityScorer
from .trust_score import AgentGenome, Autonomy, ImpactTier, TrustScorer

app = FastAPI(
    title="Agenomics API",
    description=(
        "Genetics for AI Agents — Trust Score и Compatibility Score для "
        "автономных ИИ-агентов. Методология: см. docs/METHODOLOGY.md в репозитории."
    ),
    version="0.3.0",
)

_default_scorer = TrustScorer()
_default_compat_scorer = CompatibilityScorer()


class GenomeRequest(BaseModel):
    id: str = Field(..., description="Уникальный идентификатор агента")
    domain: Optional[str] = Field(
        None, description="Домен агента, напр. 'finance', 'support', 'content'"
    )
    domains: Optional[List[str]] = Field(
        None, description="Список доменов, если агент затрагивает несколько — Tier берётся максимальный"
    )
    autonomy: str = Field(
        "advisory", description="'advisory' (только советует) или 'autonomous' (действует сам)"
    )
    role: Optional[str] = Field(
        None, description="Роль в команде для Compatibility Score: 'standard', 'executor', 'reviewer'"
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
    risk_tolerance: Optional[float] = Field(
        None, ge=0, le=100, description="Для Compatibility Score: 0 (осторожный) - 100 (рискованный)"
    )
    social_style: Optional[float] = Field(
        None, ge=0, le=100, description="Для Compatibility Score: 0 (формальный) - 100 (неформальный/эмпатичный)"
    )
    weight_profile: str = Field(
        "default", description="Профиль весов Trust Score: 'default', 'healthcare', 'finance', 'content'"
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
    confidence: str
    confidence_ratio: float
    attribution: str


class CompatibilityRequest(BaseModel):
    agents: List[GenomeRequest] = Field(
        ..., min_length=2, description="Список из 2+ агентов для оценки совместимости"
    )
    weight_profile: str = Field(
        "default", description="Профиль весов Compatibility Score: 'default', 'safety_critical'"
    )


class PairScoreResponse(BaseModel):
    agent_a: str
    agent_b: str
    score: float
    breakdown: Dict[str, float]
    insufficient_axes: List[str]
    capped_reason: Optional[str] = None
    confidence: str
    confidence_ratio: float
    complementary_roles: bool
    attribution: str


class TeamCompatibilityResponse(BaseModel):
    average_score: float
    pairs: List[PairScoreResponse]
    weakest_pair: PairScoreResponse


def _to_genome(payload: GenomeRequest) -> AgentGenome:
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
    return AgentGenome(
        id=payload.id,
        domain=payload.domain,
        domains=payload.domains,
        autonomy=autonomy,
        role=payload.role,
        transparency=payload.transparency,
        bias_control=payload.bias_control,
        data_safety=payload.data_safety,
        drift_rate=payload.drift_rate,
        has_ledger=payload.has_ledger,
        accountability_override=payload.accountability_override,
        tier_override=tier_override,
        risk_tolerance=payload.risk_tolerance,
        social_style=payload.social_style,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "agenomics-api", "version": "0.3.0"}


@app.get("/")
def root() -> dict:
    return {
        "name": "Agenomics API",
        "description": "Genetics for AI Agents — Trust Score & Compatibility Score methodology.",
        "endpoints": {
            "POST /score": "Рассчитать Trust Score для генома агента",
            "POST /compatibility": "Рассчитать совместимость 2+ агентов в команде",
            "GET /health": "Проверка работоспособности",
        },
        "docs": "/docs",  # автоматическая Swagger-документация FastAPI
    }


@app.post("/score", response_model=TrustScoreResponse)
def score_agent(payload: GenomeRequest) -> TrustScoreResponse:
    genome = _to_genome(payload)
    try:
        scorer = TrustScorer(weight_profile=payload.weight_profile) if payload.weight_profile != "default" else _default_scorer
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = scorer.score(genome)

    return TrustScoreResponse(
        id=payload.id,
        tier=int(genome.tier.value),
        autonomy=genome.autonomy.value,
        score=result.score,
        label=result.label,
        breakdown=result.breakdown,
        insufficient_axes=result.insufficient_axes,
        capped_reason=result.capped_reason,
        recommendations=result.recommendations,
        confidence=result.confidence,
        confidence_ratio=result.confidence_ratio,
        attribution=result.attribution,
    )


@app.post("/compatibility", response_model=TeamCompatibilityResponse)
def score_compatibility(payload: CompatibilityRequest) -> TeamCompatibilityResponse:
    genomes = [_to_genome(a) for a in payload.agents]
    try:
        scorer = (
            CompatibilityScorer(weight_profile=payload.weight_profile)
            if payload.weight_profile != "default"
            else _default_compat_scorer
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = scorer.score_team(genomes)

    def _to_pair_response(p) -> PairScoreResponse:
        return PairScoreResponse(
            agent_a=p.agent_a,
            agent_b=p.agent_b,
            score=p.score,
            breakdown=p.breakdown,
            insufficient_axes=p.insufficient_axes,
            capped_reason=p.capped_reason,
            confidence=p.confidence,
            confidence_ratio=p.confidence_ratio,
            complementary_roles=p.complementary_roles,
            attribution=p.attribution,
        )

    return TeamCompatibilityResponse(
        average_score=result.average_score,
        pairs=[_to_pair_response(p) for p in result.pairs],
        weakest_pair=_to_pair_response(result.weakest_pair),
    )
