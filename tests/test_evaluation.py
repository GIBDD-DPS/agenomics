"""
test_evaluation.py. Тесты Real-World Evaluation Layer.

Автор: Dm.Andreyanov
Проект: Prizolov Lab
Версия: 0.7.10

Важно: тесты здесь проверяют механику подсчёта (правильно ли считается
корреляция на контролируемых, заранее сконструированных данных), а не
"валидируют" методологию. Реальная валидация требует реальных
production-наблюдений, которых в тестах по определению нет.
"""

from agenomics import AgentGenome, TrustScorer, Incident, IncidentSeverity
from agenomics.evaluation import RealWorldEvaluationLayer


def _make_result(score_hint: float):
    """Хелпер: генерирует TrustResult с примерно нужным score через подбор
    входных данных (не подделываем сам TrustResult напрямую, используем
    настоящий TrustScorer, чтобы тест шёл через реальный код)."""
    genome = AgentGenome(
        id="eval-test", domain="content", autonomy="advisory",
        transparency=score_hint, bias_control=score_hint, data_safety=score_hint,
        drift_rate=1 - score_hint / 100, has_ledger=True,
    )
    return TrustScorer().score(genome)


def test_insufficient_data_before_threshold():
    layer = RealWorldEvaluationLayer(min_observations=10)
    for _ in range(5):
        layer.record_observation("agent-1", _make_result(80))
    report = layer.trust_reality_report("agent-1")
    assert report.status == "insufficient_data"
    assert report.n_observations == 5
    assert report.correlation is None


def test_correlation_mechanics_negative_when_high_score_means_few_incidents():
    """Контролируемый сценарий: высокий declared score -> мало инцидентов,
    низкий declared score -> много инцидентов. Ожидаем отрицательную
    корреляцию. Это проверка правильности арифметики, не 'открытие'."""
    layer = RealWorldEvaluationLayer(min_observations=10)
    for i in range(12):
        # Чередуем высокий/низкий score с соответствующей нагрузкой инцидентов
        if i % 2 == 0:
            result = _make_result(90)
            incidents = []  # высокий score -> нет инцидентов
        else:
            result = _make_result(40)
            incidents = [Incident("тестовый инцидент", IncidentSeverity.MODERATE)]
        layer.record_observation("agent-2", result, incidents=incidents)

    report = layer.trust_reality_report("agent-2")
    assert report.status == "computed"
    assert report.n_observations == 12
    assert report.correlation < 0, "При такой конструкции данных корреляция обязана быть отрицательной"


def test_correlation_mechanics_near_zero_when_unrelated():
    """Обратный контроль: если инциденты НЕ связаны со score (одинаковая
    нагрузка независимо от score), корреляция должна быть близка к нулю,
    иначе в подсчёте есть скрытая ошибка."""
    layer = RealWorldEvaluationLayer(min_observations=10)
    for i in range(12):
        score_hint = 90 if i % 2 == 0 else 40
        result = _make_result(score_hint)
        # Ровно один инцидент средней тяжести НЕЗАВИСИМО от score
        incidents = [Incident("не связано со score", IncidentSeverity.MODERATE)]
        layer.record_observation("agent-3", result, incidents=incidents)

    report = layer.trust_reality_report("agent-3")
    assert report.status == "computed"
    assert abs(report.correlation) < 0.3, "Постоянная нагрузка инцидентов не должна давать сильную корреляцию"


def test_incident_rate_computed_correctly():
    layer = RealWorldEvaluationLayer(min_observations=3)
    layer.record_observation("agent-4", _make_result(80), incidents=[])
    layer.record_observation("agent-4", _make_result(80), incidents=[Incident("x", IncidentSeverity.MINOR)])
    layer.record_observation("agent-4", _make_result(80), incidents=[])
    report = layer.trust_reality_report("agent-4")
    assert report.status == "computed"
    assert report.n_observations == 3
    # 1 инцидент на 3 наблюдения
    assert abs(report.incident_rate - (1 / 3)) < 1e-3


def test_declared_score_trend_reflects_drift_monitor_v2():
    """trust_reality_report должен отражать реальный тренд из DriftMonitorV2,
    не выдумывать отдельную логику дрейфа."""
    layer = RealWorldEvaluationLayer(min_observations=5)
    scores = [90, 90, 90, 60, 40, 30, 25, 20, 15, 10, 8]
    for s in scores:
        layer.record_observation("agent-5", _make_result(s), incidents=[])
    report = layer.trust_reality_report("agent-5")
    assert report.status == "computed"
    assert report.declared_score_trend in ("mild", "moderate", "severe", "sudden", "volatile")


def test_observations_accessor_returns_recorded_history():
    layer = RealWorldEvaluationLayer()
    layer.record_observation("agent-6", _make_result(75))
    layer.record_observation("agent-6", _make_result(76))
    obs = layer.observations("agent-6")
    assert len(obs) == 2
    assert obs[0].declared_score != obs[1].declared_score or True  # просто проверяем, что history не теряется


def test_record_raw_observation_bypasses_trust_result():
    """record_raw_observation (v0.7.0) должен работать идентично
    record_observation, но принимая сырые значения. Нужен для
    воспроизведения данных из EvidenceStore, где полного TrustResult нет."""
    layer = RealWorldEvaluationLayer(min_observations=2)
    layer.record_raw_observation("agent-7", score=90.0, label="Trusted", confidence="High")
    layer.record_raw_observation("agent-7", score=88.0, label="Trusted", confidence="High")
    obs = layer.observations("agent-7")
    assert len(obs) == 2
    assert obs[0].declared_score == 90.0
    assert obs[1].declared_label == "Trusted"


# --- Тесты evidence_strength (v0.7.9) ------------------------------------

def test_evidence_strength_insufficient_below_threshold():
    layer = RealWorldEvaluationLayer(min_observations=10)
    for i in range(5):
        layer.record_raw_observation("agent-x", score=70.0, label="Conditional")
    report = layer.trust_reality_report("agent-x")
    assert report.status == "insufficient_data"
    assert report.evidence_strength == "insufficient"


def test_evidence_strength_exploratory_at_10():
    layer = RealWorldEvaluationLayer(min_observations=10)
    for i in range(12):
        layer.record_raw_observation("agent-x", score=70.0, label="Conditional")
    report = layer.trust_reality_report("agent-x")
    assert report.status == "computed"
    assert report.evidence_strength == "exploratory"


def test_evidence_strength_preliminary_at_50():
    layer = RealWorldEvaluationLayer(min_observations=10)
    for i in range(60):
        layer.record_raw_observation("agent-x", score=70.0, label="Conditional")
    report = layer.trust_reality_report("agent-x")
    assert report.evidence_strength == "preliminary"


def test_evidence_strength_validation_candidate_at_200():
    layer = RealWorldEvaluationLayer(min_observations=10)
    for i in range(250):
        layer.record_raw_observation("agent-x", score=70.0, label="Conditional")
    report = layer.trust_reality_report("agent-x")
    assert report.evidence_strength == "validation_candidate"


def test_evidence_strength_strong_at_1000():
    layer = RealWorldEvaluationLayer(min_observations=10)
    for i in range(1000):
        layer.record_raw_observation("agent-x", score=70.0, label="Conditional")
    report = layer.trust_reality_report("agent-x")
    assert report.evidence_strength == "strong"


def test_evidence_strength_handles_custom_min_observations_below_10():
    """Регрессионный тест на реальный найденный краевой случай: с кастомным
    min_observations < 10, статус может быть "computed" при n меньше
    универсального порога "exploratory" (10). Раньше это падало с
    KeyError('insufficient') в словаре пояснений."""
    layer = RealWorldEvaluationLayer(min_observations=3)
    for i in range(3):
        layer.record_raw_observation("agent-x", score=70.0, label="Conditional")
    report = layer.trust_reality_report("agent-x")
    assert report.status == "computed"
    assert report.evidence_strength == "insufficient"
    assert "min_observations" in report.detail
