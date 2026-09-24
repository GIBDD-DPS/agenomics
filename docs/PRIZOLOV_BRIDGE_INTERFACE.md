# Интерфейс-контракт: Agenomics ↔ Prizolov Market

**Автор**: Dm.Andreyanov · **Проект**: Prizolov Lab
**Статус**: НАБРОСОК ИНТЕРФЕЙСА, НЕ РАБОЧАЯ ИНТЕГРАЦИЯ

## Честная оговорка

У меня нет доступа к реальному коду `prizolov_market`. `Metrics_Agent`,
`Trace_Collector`, `Trigger` и другие имена из обсуждения не
существуют в моём контексте как реальный API, это предполагаемые
названия. Поэтому ниже, не готовый модуль `prizolov-agenomics-bridge`,
а **интерфейс со стороны Agenomics**, который ваш реальный оркестратор
сможет реализовать. Выдумывать поведение `prizolov_market` изнутри
было бы нечестной имитацией интеграции. То же самое правило
применяется ко всем данным и метрикам в этом проекте.

## Что можно взять уже сейчас (реальный, протестированный код)

Всё, что нужно с "нашей" стороны, уже существует и работает:

```python
from agenomics import (
    AgentGenome, TrustScorer, DriftMonitorV2,
    EvidenceStore, RealWorldEvaluationLayer,
)
from agenomics.per_axis_drift import PerAxisDriftMonitor

scorer = TrustScorer(weight_profile="finance")  # или свой профиль под sports_prediction
genome = AgentGenome(id=agent.id, domain="sports_prediction", autonomy="autonomous", ...)
result = scorer.score(genome)

drift_monitor = DriftMonitorV2()
drift_monitor.record(agent.id, result.score)
drift_report = drift_monitor.report(agent.id)

if drift_report.alert and drift_report.severity in ("severe", "sudden"):
    # здесь вызывается ВАШ реальный Trigger.rollback_to_previous_version(),
    # которого нет в этом репозитории
    pass
```

Это уже рабочий псевдокод из вашего сообщения, просто с реальными
именами Agenomics API вместо `TrustScorer.calculate()`/`DriftMonitor.track()`
(которых как статических методов не существует, обе используются как
экземпляры класса, см. примеры в README).

## Интерфейс, который мог бы реализовать ваш оркестратор

```python
from typing import Protocol
from agenomics import TrustResult
from agenomics.drift import DriftReportV2


class AgentLifecycleHook(Protocol):
    """Контракт со стороны Agenomics. То, что ваш оркестратор мог бы
    вызывать на разных этапах жизненного цикла агента. Это Protocol
    (структурная типизация), не ABC. Реализовывать необязательно
    целиком, только нужные методы."""

    def on_genome_extracted(self, agent_id: str, genome_hash: str) -> None:
        """Вызывается после извлечения генома из промпта агента
        (например, через PromptToGenomeExtractor). Принимает хэш, а не
        сам геном целиком: сам геном может быть чувствительным, хэш
        достаточен, чтобы связать наблюдение с конкретной версией
        генома, см. GenomeLedger."""
        ...

    def on_trust_scored(self, agent_id: str, result: TrustResult) -> None:
        """Вызывается после каждого расчёта Trust Score."""
        ...

    def on_drift_alert(self, agent_id: str, report: DriftReportV2) -> None:
        """Вызывается, когда DriftMonitorV2 поднимает alert. Здесь
        естественное место для вызова вашего Trigger.rollback_to_previous_version(),
        но САМ вызов остаётся на стороне вашего оркестратора, Agenomics
        не может и не должен управлять жизненным циклом чужой системы."""
        ...
```

## Готовая реализация приёмной стороны (v0.7.4)

Интерфейс `AgentLifecycleHook` выше был только протоколом (Protocol с
`...` вместо тела методов). Теперь есть его реальная, протестированная
реализация: `agenomics.EvidenceStoreHook`. Она ничего не знает о
`prizolov_market` и не должна знать: ей достаточно, чтобы её три метода
вызывали в подходящие моменты вашего оркестратора.

```python
from agenomics import EvidenceStore, EvidenceStoreHook

store = EvidenceStore("agenomics_evidence.db")
hook = EvidenceStoreHook(store, source="sports_prediction_agent_v3")

# После извлечения генома
hook.on_genome_extracted(agent.id, genome_hash="...")

# После каждого расчёта Trust Score
hook.on_trust_scored(agent.id, result)

# Когда DriftMonitorV2 поднимает alert
if drift_report.alert:
    hook.on_drift_alert(agent.id, drift_report)
```

Единственное, чего всё ещё не хватает, это вызова этих трёх методов
**из вашего кода**, в нужных местах вашего оркестратора, а это и есть
та часть, для которой нужны реальные сигнатуры `prizolov_market`.

## Маркер исхода задачи (v0.8.0)

Три метода выше сообщают факты: геном извлечён, score посчитан, дрейф
замечен. Для проверки, предсказывает ли score что-нибудь, нужен ещё и
исход: решил ли агент задачу. `on_task_outcome()` дописывает его в то же
наблюдение, в котором score записан **до** выполнения задачи:

```python
from agenomics import Incident, IncidentCategory, IncidentSeverity

obs_id = hook.on_trust_scored(
    agent.id, result,
    model_version="groq/openai/gpt-oss-20b", prompt_version="v3",
)                                    # до выполнения задачи

prediction = agent.run(task)         # ваш код

hook.on_task_outcome(obs_id, "failure", [
    Incident("прогноз не сбылся", IncidentSeverity.MODERATE,
             category=IncidentCategory.RESPONSE_QUALITY),
])                                   # когда исход стал известен
```

Порядок важен: если считать score после задачи, по тем же данным, что
определили её исход, их связь возникает по построению (см. CHANGELOG
0.7.12). Исход пишется один раз, повторный вызов это `ValueError`.

`outcome`: `"success"`, `"failure"` или `"partial"`. Что считать успехом,
решает ваша система (сбылся прогноз, пользователь принял ответ, тикет
закрыт), Agenomics этого знать не может. Файл маркеров на стороне
вашего агента (`instrumentation_block.md`) в этом репозитории не
хранится: вызовы `on_task_outcome()` нужно добавить туда, где ваш
оркестратор узнаёт исход.

## Доноры, предсказания и исходы (v0.9.0)

`on_task_outcome()` отвечает на вопрос «чем закончилась задача», но не
«кто это сообщил». Для проверки Trust Score важно и то, и другое:
100 оценок одного LLM-судьи это не 100 независимых подтверждений.
Полная схема (AEP-001, раздел 7) работает напрямую через `EvidenceStore`:

```python
store = EvidenceStore("agenomics_evidence.db")

# Один раз при старте: кто будет сообщать доказательства
store.register_donor("claude_judge.v1", "judge", "Claude safety judge",
                     independence_group="anthropic_llm", provider="Anthropic", model="...")
store.register_donor("sec_team", "human", "Security engineer", independence_group="human")
store.register_donor("match_results", "outcome", "Итог матча из фида",
                     independence_group="sports_feed")

# До задачи: score заморожен, предсказание записано
obs_id = hook.on_trust_scored(agent.id, result, model_version="...", prompt_version="v3")
pred_id = store.record_prediction(obs_id, target="prediction_wrong", horizon="match_end")

prediction = agent.run(task)                          # ваш код

# После: доказательства и исходы от разных доноров, противоречия сохраняются
store.record_evidence(obs_id, "claude_judge.v1", "behavioral_evaluation", "safe", "Q3", confidence=0.8)
store.record_outcome(pred_id, "match_results", "prediction_wrong", occurred=True,
                     verification="ground_truth")

print(store.evidence_profile(agent.id))               # объём, качество, независимость
```

`record_outcome()` не примет исход, наблюдённый раньше заморозки
предсказания. Новая версия модели судьи регистрируется под новым
`donor_id`: её оценки нельзя смешивать со старыми как один источник.

## Почему я не пишу это как готовый пакет `prizolov-agenomics-bridge`

1. Я не вижу реальных сигнатур `Metrics_Agent`/`Trace_Collector`/`Trigger`,
   поэтому любой код против них был бы совместим только случайно
2. Даже интерфейс выше, это гипотеза о том, как могла бы выглядеть
   интеграция, а не спецификация вашей системы
3. Если вы поделитесь реальными сигнатурами `prizolov_market` (хотя бы
   заголовками классов/методов, без внутренней логики), я смогу
   написать настоящий, а не гипотетический мост, с тестами против
   моков этих сигнатур

## Что действительно можно сделать прямо сейчас, без ожидания моста

`agenomics` уже `pip install`-ится и не требует никакой интеграции,
чтобы начать использоваться внутри `prizolov_market` напрямую. Импорт
как обычной библиотеки, без отдельного пакета-моста. Отдельный пакет
`prizolov-agenomics-bridge` имеет смысл, только если предполагается
переиспользование этой интеграции в нескольких разных системах, а не
только в `prizolov_market`.
