"""
phenotype.py — Genome Schema и Phenotype (AGENOMICS SPECIFICATION v1.0).

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.5.0

Формализует два понятия спецификации, которых не было явно в v0.1-0.4:

1. Genome Schema — формальное описание полей AgentGenome (тип, диапазон,
   обязательность) для интроспекции/документации/валидации извне.

2. Phenotype — "выраженные" значения осей ПОСЛЕ взаимодействия генома
   с контекстом (Impact Tier), НО ДО применения весов Trust Model.
   Ключевая идея: два агента с ОДИНАКОВЫМ Genome, но в разном контексте
   (разный Tier), будут иметь РАЗНЫЙ Phenotype — потому что tier-множитель
   штрафует Predictability/Accountability по-разному. Это и есть
   биологическая аналогия "генотип формируется средой в конкретный
   фенотип", формализованная как отдельный, тестируемый шаг конвейера:

       Genome → Genome Schema (валидация) → Phenotype (генотип + контекст)
       → Trust Model (веса + потолки → Score)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .trust_score import AgentGenome, ImpactTier, TrustScorer

# --- Genome Schema -----------------------------------------------------------


@dataclass
class FieldSpec:
    name: str
    type: str
    required: bool
    value_range: Optional[Tuple[float, float]] = None
    description: str = ""


GENOME_SCHEMA: List[FieldSpec] = [
    FieldSpec("id", "str", True, description="Уникальный идентификатор агента"),
    FieldSpec("domain", "str | null", False, description="Домен применения (одиночный)"),
    FieldSpec("domains", "list[str] | null", False, description="Множественные домены — Tier берётся максимальный"),
    FieldSpec("autonomy", "enum[advisory, autonomous]", False, description="Уровень автономности, по умолчанию advisory"),
    FieldSpec("role", "str | null", False, description="Роль в команде для Compatibility Model (напр. executor/reviewer)"),
    FieldSpec("transparency", "float | null", False, (0, 100), "Ось Trust Model"),
    FieldSpec("bias_control", "float | null", False, (0, 100), "Ось Trust Model / Compatibility Model (этика)"),
    FieldSpec("data_safety", "float | null", False, (0, 100), "Ось Trust Model"),
    FieldSpec("drift_rate", "float | null", False, (0, 1), "Источник для Predictability = (1 - drift_rate) * 100"),
    FieldSpec("has_ledger", "bool", False, description="Источник для Accountability (90 если True, иначе 30), default False"),
    FieldSpec("accountability_override", "float | null", False, (0, 100), "Ручная оценка Accountability в обход has_ledger"),
    FieldSpec("risk_tolerance", "float | null", False, (0, 100), "Ось Compatibility Model"),
    FieldSpec("social_style", "float | null", False, (0, 100), "Ось Compatibility Model"),
    FieldSpec("tier_override", "enum[1,2,3] | null", False, description="Принудительный Impact Tier в обход авто-классификации по domain/domains"),
]


def describe_genome_schema() -> List[Dict[str, Any]]:
    """Machine-readable описание Genome Schema — для документации, API,
    автогенерации форм ввода и т.п. Источник истины — сам GENOME_SCHEMA,
    синхронизирован вручную с валидацией в AgentGenome.__post_init__."""
    return [
        {
            "name": f.name,
            "type": f.type,
            "required": f.required,
            "range": f.value_range,
            "description": f.description,
        }
        for f in GENOME_SCHEMA
    ]


# --- Phenotype -----------------------------------------------------------


@dataclass
class Phenotype:
    agent_id: str
    tier: ImpactTier
    expressed_traits: Dict[str, float]  # tier-adjusted, ДО весов Trust Model
    insufficient_axes: List[str] = field(default_factory=list)


def compute_phenotype(genome: AgentGenome) -> Phenotype:
    """
    Вычисляет Phenotype агента: значения 5 осей после применения
    tier-множителя (тот же механизм, что использует TrustScorer.score()),
    но БЕЗ весов и БЕЗ потолка автономности — это отдельный концептуальный
    шаг ("как проявляется геном в данном контексте"), предшествующий
    собственно скорингу ("как мы оцениваем это проявление").

    Переиспользует TrustScorer._apply_tier_penalty(), чтобы не дублировать
    логику tier-множителя в двух местах (риск рассинхрона формул).
    """
    scorer = TrustScorer()  # веса не используются, нужен только tier-penalty метод
    raw = {
        "transparency": genome.transparency,
        "bias_control": genome.bias_control,
        "data_safety": genome.data_safety,
        "predictability": genome.predictability,
        "accountability": genome.accountability,
    }
    insufficient = []
    resolved = {}
    for axis, value in raw.items():
        if value is None:
            insufficient.append(axis)
            resolved[axis] = 50.0
        else:
            resolved[axis] = value

    tier = genome.tier
    resolved["predictability"] = scorer._apply_tier_penalty(resolved["predictability"], tier)
    resolved["accountability"] = scorer._apply_tier_penalty(resolved["accountability"], tier)

    return Phenotype(
        agent_id=genome.id,
        tier=tier,
        expressed_traits=resolved,
        insufficient_axes=insufficient,
    )
