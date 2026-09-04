"""
metrics.py — метрики Agenomics Synthetic Benchmark Suite.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.6.0

Каждая метрика возвращает BenchmarkResult с явным полем `status`:
  - "computed"       — реально вычислено на синтетических данных
  - "not_computable" — честно помечено как невозможное без реальных
                        production-данных (см. detail)

См. benchmark/__init__.py для объяснения, почему это разграничение
принципиально важно.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agenomics import (
    AgentGenome, TrustScorer, CompatibilityScorer, DriftMonitor,
)

from .scenarios import (
    quality_spectrum_genomes,
    drift_rate_spectrum_genomes,
    compatibility_ground_truth_cases,
    drift_timeseries_with_known_degradation,
    generate_compatibility_ground_truth,
    DRIFT_SCENARIOS_V2,
)
from agenomics.drift import DriftMonitorV2


@dataclass
class BenchmarkResult:
    metric: str
    status: str  # "computed" | "not_computable"
    value: Optional[float] = None
    detail: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)


def _pearson_correlation(xs: List[float], ys: List[float]) -> float:
    """Чистый Python, без numpy/scipy — ядро методологии без внешних
    зависимостей, и benchmark следует тому же принципу."""
    n = len(xs)
    if n == 0 or n != len(ys):
        raise ValueError("xs и ys должны быть одинаковой ненулевой длины")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = (var_x * var_y) ** 0.5
    if denom == 0:
        return 0.0
    return cov / denom


# --- 1. Reproducibility ------------------------------------------------------

def measure_reproducibility(n_runs: int = 50) -> BenchmarkResult:
    """
    Запускает один и тот же геном через TrustScorer n_runs раз, проверяет,
    что результат идентичен КАЖДЫЙ раз (score, label, breakdown).

    Это единственная метрика в списке, где ожидается ровно 1.0 — не
    потому что формула "хорошая", а потому что она детерминированная
    функция, а не LLM-суждение. Это само по себе значимое отличие от
    подходов на основе LLM-as-judge (там reproducibility обычно < 1.0).
    """
    genome = AgentGenome(
        id="repro-test", domain="finance", autonomy="autonomous",
        transparency=72, bias_control=68, data_safety=81,
        drift_rate=0.22, has_ledger=False,
    )
    scorer = TrustScorer()
    results = [scorer.score(genome) for _ in range(n_runs)]
    first = results[0]
    identical = all(
        r.score == first.score and r.label == first.label and r.breakdown == first.breakdown
        for r in results
    )
    return BenchmarkResult(
        metric="Reproducibility",
        status="computed",
        value=1.0 if identical else 0.0,
        detail=(
            f"{n_runs} независимых запусков одного генома. "
            f"{'Все результаты идентичны.' if identical else 'ОБНАРУЖЕНО РАСХОЖДЕНИЕ — баг, формула не должна быть недетерминированной.'}"
        ),
        raw_data={"n_runs": n_runs, "identical": identical},
    )


# --- 2. Behavioral Predictability (formula consistency) ---------------------

def measure_behavioral_predictability_consistency() -> BenchmarkResult:
    """
    ВНИМАНИЕ: тестирует внутреннюю согласованность формулы
    (монотонность Predictability относительно drift_rate), А НЕ то,
    насколько реальное поведение агентов соответствует их Genome —
    для последнего нет производственных данных ни у кого.
    """
    scenarios = drift_rate_spectrum_genomes()
    scorer = TrustScorer()
    drift_rates = []
    predictability_scores = []
    for genome, drift_rate in scenarios:
        result = scorer.score(genome)
        drift_rates.append(drift_rate)
        predictability_scores.append(result.breakdown["predictability"])

    # Ожидаем ОТРИЦАТЕЛЬНУЮ корреляцию: выше drift_rate -> ниже Predictability
    correlation = _pearson_correlation(drift_rates, predictability_scores)

    return BenchmarkResult(
        metric="Behavioral Predictability (formula consistency)",
        status="computed",
        value=correlation,
        detail=(
            f"Корреляция Пирсона между drift_rate и итоговым Predictability "
            f"на {len(scenarios)} синтетических точках: {correlation:.4f} "
            f"(ожидается близко к -1.0 — монотонное убывание). "
            f"Это НЕ валидация против реального поведения агентов."
        ),
        raw_data={"n_points": len(scenarios)},
    )


# --- 3. Trust Calibration (formula consistency) ------------------------------

def measure_trust_calibration_consistency() -> BenchmarkResult:
    """
    ВНИМАНИЕ: тестирует, монотонно ли растёт Trust Score вместе с
    синтетически заданным "истинным качеством" агента — А НЕ то,
    предсказывает ли Score реальные инциденты в проде.
    """
    scenarios = quality_spectrum_genomes()
    scorer = TrustScorer()
    qualities = []
    scores = []
    for genome, intended_quality in scenarios:
        result = scorer.score(genome)
        qualities.append(intended_quality)
        scores.append(result.score)

    correlation = _pearson_correlation(qualities, scores)

    return BenchmarkResult(
        metric="Trust Calibration (formula consistency)",
        status="computed",
        value=correlation,
        detail=(
            f"Корреляция Пирсона между синтетическим 'истинным качеством' "
            f"и Trust Score на {len(scenarios)} точках: {correlation:.4f} "
            f"(ожидается близко к +1.0). Это проверка внутренней логики "
            f"формулы, НЕ калибровка против реальных исходов."
        ),
        raw_data={"n_points": len(scenarios)},
    )


# --- 4. Compatibility Accuracy (ranking on known cases) ----------------------

def measure_compatibility_accuracy() -> BenchmarkResult:
    """
    Проверяет, ранжирует ли CompatibilityScorer заведомо "compatible"
    пары систематически выше, чем заведомо "conflicting" — на вручную
    сконструированных случаях (см. scenarios.compatibility_ground_truth_cases).
    НЕ валидация против реальных конфликтов агентов в проде.
    """
    cases = compatibility_ground_truth_cases()
    scorer = CompatibilityScorer()

    compatible_scores = []
    conflicting_scores = []
    for case in cases:
        result = scorer.score_pair(case.genome_a, case.genome_b)
        if case.label == "compatible":
            compatible_scores.append(result.score)
        else:
            conflicting_scores.append(result.score)

    if not compatible_scores or not conflicting_scores:
        return BenchmarkResult(
            metric="Compatibility Accuracy",
            status="not_computable",
            detail="Нужны случаи обоих классов (compatible и conflicting).",
        )

    min_compatible = min(compatible_scores)
    max_conflicting = max(conflicting_scores)
    correctly_separated = min_compatible > max_conflicting

    # Accuracy как доля пар, правильно ранжированных относительно
    # межгруппового порога (простая, но честная метрика на 4 точках)
    correct = sum(1 for s in compatible_scores if s > max(conflicting_scores))
    correct += sum(1 for s in conflicting_scores if s < min(compatible_scores))
    accuracy = correct / (len(compatible_scores) + len(conflicting_scores))

    return BenchmarkResult(
        metric="Compatibility Accuracy",
        status="computed",
        value=accuracy,
        detail=(
            f"{len(cases)} вручную сконструированных случаев (не из реальных "
            f"инцидентов). Compatible scores: {compatible_scores}, "
            f"Conflicting scores: {conflicting_scores}. "
            f"Полное разделение классов: {correctly_separated}."
        ),
        raw_data={
            "compatible_scores": compatible_scores,
            "conflicting_scores": conflicting_scores,
            "fully_separated": correctly_separated,
        },
    )


# --- 4b. Compatibility Accuracy v2 (расширенный ground truth, n=270) -------

def measure_compatibility_accuracy_v2(cases_per_category: int = 30) -> BenchmarkResult:
    """
    То же самое, что measure_compatibility_accuracy(), но на систематически
    сгенерированном наборе из 9 категорий x cases_per_category случаев
    (по умолчанию 270), а не на 4 вручную подобранных случаях v0.1.

    Категории 'near_threshold' и 'neutral' размечены как "ambiguous" и
    ИСКЛЮЧЕНЫ из бинарной accuracy — честно, а не потому что портят цифру:
    они специально сконструированы как пограничные, и ожидать от них
    чёткого попадания в "compatible"/"conflicting" было бы некорректной
    постановкой эксперимента.
    """
    cases = generate_compatibility_ground_truth(cases_per_category)
    scorer = CompatibilityScorer()

    by_category: Dict[str, List[float]] = {}
    compatible_scores: List[float] = []
    conflicting_scores: List[float] = []

    for case in cases:
        result = scorer.score_pair(case.genome_a, case.genome_b)
        by_category.setdefault(case.category, []).append(result.score)
        if case.expected_label == "compatible":
            compatible_scores.append(result.score)
        elif case.expected_label == "conflicting":
            conflicting_scores.append(result.score)
        # "ambiguous" сознательно не участвует в бинарной метрике

    if not compatible_scores or not conflicting_scores:
        return BenchmarkResult(
            metric="Compatibility Accuracy v2 (n={})".format(len(cases)),
            status="not_computable",
            detail="Нужны случаи обоих классов compatible/conflicting.",
        )

    min_compatible = min(compatible_scores)
    max_conflicting = max(conflicting_scores)
    fully_separated = min_compatible > max_conflicting

    correct = sum(1 for s in compatible_scores if s > max_conflicting)
    correct += sum(1 for s in conflicting_scores if s < min_compatible)
    accuracy = correct / (len(compatible_scores) + len(conflicting_scores))

    category_summary = {
        cat: {"n": len(scores), "min": round(min(scores), 1), "max": round(max(scores), 1),
              "avg": round(sum(scores) / len(scores), 1)}
        for cat, scores in by_category.items()
    }

    return BenchmarkResult(
        metric=f"Compatibility Accuracy v2 (n={len(cases)})",
        status="computed",
        value=accuracy,
        detail=(
            f"{len(cases)} систематически сгенерированных случаев (9 категорий, "
            f"не 4 вручную подобранных, как в v0.1). Полное разделение "
            f"compatible/conflicting: {fully_separated} "
            f"(min_compatible={min_compatible:.1f}, max_conflicting={max_conflicting:.1f}). "
            f"Категории 'near_threshold' и 'neutral' исключены из accuracy как "
            f"намеренно пограничные — см. category_summary в raw_data."
        ),
        raw_data={"category_summary": category_summary, "fully_separated": fully_separated},
    )


# --- 5b. Drift Detection v2 (7 сценариев, DriftMonitorV2) -------------------

def measure_drift_detection_v2() -> BenchmarkResult:
    """
    То же назначение, что measure_drift_detection_lag(), но на
    DriftMonitorV2 и 7 сценариях вместо 3 уровней тяжести на DriftMonitor v1.
    Явно проверяет то, что v1 не умел: false positive rate на 'no_drift'
    и корректное различение 'sudden' от 'oscillation' ('volatile').
    """
    results_by_scenario = {}
    for name, generator in DRIFT_SCENARIOS_V2.items():
        scores = generator()
        monitor = DriftMonitorV2()
        first_alert_at = None
        any_recovered = False
        severities_seen = set()
        for i, s in enumerate(scores):
            monitor.record("synthetic-agent-v2", s)
            r = monitor.report("synthetic-agent-v2")
            if r.severity != "insufficient_data":
                severities_seen.add(r.severity)
                if r.alert and first_alert_at is None:
                    first_alert_at = i
                if r.recovered:
                    any_recovered = True
        results_by_scenario[name] = {
            "first_alert_at": first_alert_at,
            "recovered": any_recovered,
            "severities_seen": sorted(severities_seen),
        }

    false_positive = results_by_scenario["no_drift"]["first_alert_at"] is not None
    mild_detected = results_by_scenario["mild"]["first_alert_at"] is not None
    recovery_detected = results_by_scenario["recovery"]["recovered"]
    oscillation_clean = not any(
        s in results_by_scenario["oscillation"]["severities_seen"] for s in ("severe", "moderate")
    )

    all_good = not false_positive and mild_detected and recovery_detected and oscillation_clean

    return BenchmarkResult(
        metric="Drift Detection v2 (7 scenarios)",
        status="computed",
        value=1.0 if all_good else 0.0,
        detail=(
            f"no_drift false positive: {false_positive} (должно быть False). "
            f"mild обнаружена: {mild_detected} (в v1 была НЕ обнаружена вовсе — "
            f"главное исправление v2). recovery обнаружено: {recovery_detected}. "
            f"oscillation не даёт ложных severe/moderate: {oscillation_clean}. "
            f"Известный transient: первые ~2 шага oscillation (до заполнения "
            f"rolling_window) могут классифицироваться как 'sudden' вместо "
            f"'volatile' — см. benchmark/BENCHMARKS.md."
        ),
        raw_data=results_by_scenario,
    )




def measure_drift_detection_lag() -> BenchmarkResult:
    """
    Для каждого уровня тяжести деградации (mild/moderate/severe) строит
    синтетический временной ряд с известным шагом начала деградации и
    измеряет, через сколько шагов ПОСЛЕ реального начала DriftMonitor
    поднимает alert=True. Меньше — лучше (быстрее обнаружение).
    """
    lags = {}
    for severity in ("mild", "moderate", "severe"):
        scores, degrade_at = drift_timeseries_with_known_degradation(
            degrade_at_step=5, length=15, severity=severity
        )
        monitor = DriftMonitor()
        detected_at = None
        for step, score in enumerate(scores):
            monitor.record("synthetic-agent", score)
            if step >= 2:  # _MIN_SNAPSHOTS_FOR_TREND
                report = monitor.report("synthetic-agent")
                if report.alert and detected_at is None:
                    detected_at = step
        lag = (detected_at - degrade_at) if detected_at is not None else None
        lags[severity] = lag

    computable_lags = [v for v in lags.values() if v is not None]
    avg_lag = sum(computable_lags) / len(computable_lags) if computable_lags else None
    undetected = [severity for severity, lag in lags.items() if lag is None]

    undetected_note = (
        f"НЕ обнаружено вовсе за {15} шагов: {', '.join(undetected)} — "
        f"эвристика на основе линейного наклона (см. docs/METHODOLOGY.md, "
        f"раздел 8.1) слишком груба для слабой деградации на коротком окне."
        if undetected else "Все уровни тяжести обнаружены."
    )

    return BenchmarkResult(
        metric="Drift Detection Lag",
        status="computed" if avg_lag is not None else "not_computable",
        value=avg_lag,
        detail=(
            f"Задержка обнаружения (в шагах) после реального начала деградации, "
            f"по уровням тяжести: {lags}. {undetected_note}"
        ),
        raw_data={"lags_by_severity": lags, "undetected_severities": undetected},
    )


# --- 6. Incident Correlation — ЧЕСТНО НЕ ВЫЧИСЛИМО ---------------------------

def measure_incident_correlation() -> BenchmarkResult:
    """
    НЕ вычисляется синтетически. Вычисление корреляции между Trust Score
    и реальными инцидентами по определению требует РЕАЛЬНЫХ инцидентов
    реальных агентов, накопленных через IncidentFeedback/GenomeLedger за
    продолжительный период эксплуатации. Синтетическая имитация была бы
    циркулярной (мы бы проверяли, что наша штрафная формула согласуется
    сама с собой) — то есть именно та ошибка, которой посвящена эта
    оговорка во всём проекте с самого начала (см. историю с вымышленной
    статистикой на 20 агентах в статье v1).
    """
    return BenchmarkResult(
        metric="Incident Correlation",
        status="not_computable",
        detail=(
            "Требует реальных production-инцидентов, накопленных через "
            "IncidentFeedback/GenomeLedger. Синтетическая имитация была бы "
            "циркулярной проверкой (штрафная формула проверяла бы сама себя). "
            "Если у вас есть реальные данные — присылайте через GitHub Issues, "
            "с удовольствием посчитаем эту метрику по-настоящему."
        ),
    )


# --- Запуск всех метрик -------------------------------------------------------

def run_all_benchmarks() -> List[BenchmarkResult]:
    return [
        measure_reproducibility(),
        measure_behavioral_predictability_consistency(),
        measure_trust_calibration_consistency(),
        measure_compatibility_accuracy(),
        measure_compatibility_accuracy_v2(),
        measure_drift_detection_lag(),
        measure_drift_detection_v2(),
        measure_incident_correlation(),
    ]
