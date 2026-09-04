# Как подключить Agenomics к своим реальным агентам за 15 минут

**Автор**: Dm.Andreyanov · **Проект**: Prizolov Lab

## Зачем этот гайд, а не просто README

Технически Agenomics готов к предиктивной валидности с v0.7.0: есть
`TrustScorer` (декларативная оценка), `EvidenceStore` (персистентность),
`RealWorldEvaluationLayer` (корреляция). Но у методологии сейчас
**ровно один принципиальный барьер**: реальных production-наблюдений — 0.

Не потому что их сложно собрать технически — а потому что пока никто
не подключил свои реальные агенты. Этот документ закрывает именно это:
конкретные шаги, а не архитектурное описание (оно — в
[`docs/SPECIFICATION.md`](SPECIFICATION.md) и [`docs/METHODOLOGY.md`](METHODOLOGY.md)).

Если после этого гайда вы соберёте хотя бы 10-20 реальных наблюдений —
напишите через GitHub Issues. Это будет первый реальный вклад в
`Incident Correlation`, которая сейчас честно помечена `not_computable`.

---

## Шаг 1 — Установка (1 минута)

```bash
pip install agenomics
```

## Шаг 2 — Опишите геном вашего агента один раз (2 минуты)

Не нужно ничего мерить точно с первого раза — начните с приблизительных
оценок, их можно будет уточнить позже. Главное — начать.

```python
from agenomics import AgentGenome, TrustScorer

AGENT_GENOME_TEMPLATE = dict(
    domain="support",       # ваш реальный домен: support/finance/content/...
    autonomy="autonomous",  # или "advisory", если агент только советует
    transparency=80,        # 0-100, на глаз — насколько объясним ответ агента
    bias_control=85,        # 0-100, насколько промпт ограничивает дискриминацию/манипуляцию
    data_safety=90,         # 0-100, насколько ограничен доступ к чувствительным данным
    has_ledger=True,        # ведёт ли агент журнал своих решений
)

scorer = TrustScorer()
```

Если не уверены в цифрах — используйте промпт **Trust Auditor**
(`prompts/trust_auditor_v0.2.md`) с любой LLM, скормив ей реальный
системный промпт своего агента: он вернёт структурированную оценку
по всем осям с обоснованием.

## Шаг 3 — Настройте персистентное хранилище (2 минуты)

```python
from agenomics import EvidenceStore

store = EvidenceStore("agenomics_evidence.db")  # обычный файл, переживает перезапуск
```

## Шаг 4 — Одна функция на каждый оценочный период (5 минут)

Ключевое архитектурное решение: **не оценивайте на каждый ответ агента** —
это и дорого, и статистически бессмысленно (слишком мелкая гранулярность).
Оценивайте раз в период (день/смену/N запросов) и в ЭТОТ ЖЕ момент
прикрепляйте все инциденты, случившиеся за этот период. Это даёт
корректные пары (score, incidents) для будущей корреляции.

```python
from agenomics import Incident, IncidentSeverity

def evaluate_and_log(agent_id: str, drift_rate_estimate: float, incidents=None, timestamp=None):
    """Вызывайте раз в оценочный период (например, раз в день) — считает
    Trust Score И прикрепляет инциденты, случившиеся за этот же период,
    К ОДНОМУ И ТОМУ ЖЕ наблюдению. Не создавайте отдельную запись только
    под инцидент — это исказит корреляцию искусственными нулевыми score.

    timestamp — опционально: передайте реальную историческую дату, если
    загружаете прошлые данные задним числом (см. раздел про исторические
    данные ниже); по умолчанию — текущее время."""
    genome = AgentGenome(id=agent_id, drift_rate=drift_rate_estimate, **AGENT_GENOME_TEMPLATE)
    result = scorer.score(genome)
    store.record_observation(
        agent_id=agent_id,
        declared_score=result.score,
        declared_label=result.label,
        declared_confidence=result.confidence,
        incidents=incidents or [],
        timestamp=timestamp,
    )
    return result
```

`drift_rate_estimate` — необязательно точная метрика: можно начать с
`доля запросов за период, где ответ агента вызвал сомнение / всего запросов`,
и уточнять формулу по мере накопления опыта.

## Шаг 5 — Логирование реальных инцидентов (3 минуты)

Собирайте инциденты в течение периода (например, в список в памяти или
в вашей существующей системе тикетов/жалоб), затем передавайте пачкой
в `evaluate_and_log()` на шаге 4:

```python
todays_incidents = [
    Incident("Клиент пожаловался на нерелевантный ответ", IncidentSeverity.MODERATE),
    # IncidentSeverity.MINOR / MODERATE / SEVERE — по вашей оценке серьёзности
]

evaluate_and_log("support-bot-prod", drift_rate_estimate=0.15, incidents=todays_incidents)
```

Если за период инцидентов не было — просто передайте `incidents=[]`
(или не передавайте вовсе, по умолчанию пустой список) — **это тоже
значимые данные**, не пропускайте периоды без инцидентов.

## Шаг 6 — Проверка результата (2 минуты, но не сразу)

Реальный результат появится не сегодня — нужно минимум 10 наблюдений
(`min_observations`, настраивается), то есть минимум 10 оценочных
периодов. Если период — один день, это ~2 недели.

```python
from agenomics import RealWorldEvaluationLayer, replay_into_evaluation_layer

layer = RealWorldEvaluationLayer(min_observations=10)
replay_into_evaluation_layer(store, layer, "support-bot-prod")

report = layer.trust_reality_report("support-bot-prod")
print(report.status)        # "insufficient_data" пока не накоплено достаточно
print(report.correlation)   # РЕАЛЬНАЯ корреляция — не синтетика
print(report.detail)
```

---

## Полный рабочий пример (протестирован, не псевдокод)

Ниже — тот же код целиком, на симулированных 12 днях (замените
симуляцию на вызовы из вашего реального агента):

```python
import os
from agenomics import (
    AgentGenome, TrustScorer, EvidenceStore, RealWorldEvaluationLayer,
    replay_into_evaluation_layer, Incident, IncidentSeverity,
)

AGENT_GENOME_TEMPLATE = dict(
    domain="support", autonomy="autonomous",
    transparency=80, bias_control=85, data_safety=90, has_ledger=True,
)

scorer = TrustScorer()
store = EvidenceStore("agenomics_evidence.db")


def evaluate_and_log(agent_id: str, drift_rate_estimate: float, incidents=None, timestamp=None):
    genome = AgentGenome(id=agent_id, drift_rate=drift_rate_estimate, **AGENT_GENOME_TEMPLATE)
    result = scorer.score(genome)
    store.record_observation(
        agent_id=agent_id, declared_score=result.score, declared_label=result.label,
        declared_confidence=result.confidence, incidents=incidents or [], timestamp=timestamp,
    )
    return result


# --- Замените этот блок на реальные ежедневные вызовы из вашей системы ---
for day in range(12):
    drift = 0.1 + day * 0.02
    todays_incidents = []
    if day >= 6:
        todays_incidents = [Incident(f"жалоба клиента, день {day}", IncidentSeverity.MODERATE)]
    evaluate_and_log("support-bot-prod", drift_rate_estimate=drift, incidents=todays_incidents)
# --- конец симулируемого блока ---

layer = RealWorldEvaluationLayer(min_observations=10)
replay_into_evaluation_layer(store, layer, "support-bot-prod")
report = layer.trust_reality_report("support-bot-prod")
print(report.status, report.correlation, report.detail)
```

**Реальный вывод этого примера** (можно проверить самостоятельно):

```
computed -0.866 Корреляция Пирсона между Declared Score и нагрузкой
инцидентов на 12 наблюдениях: -0.8660. Ожидается ОТРИЦАТЕЛЬНАЯ
корреляция, если методология действительно предсказательна...
```

---

## Честные ожидания

- **10-20 наблюдений — недостаточно для научных выводов**, но достаточно,
  чтобы проверить, что вся цепочка технически работает на ваших данных
- Корреляция на малой выборке будет **шумной** — не удивляйтесь, если
  число будет скакать при добавлении новых наблюдений на раннем этапе
- Если хотите использовать `IncidentFeedback` для мгновенного пересчёта
  score после конкретного инцидента (не для накопления, а для
  сиюминутной реакции) — это отдельный, более простой сценарий, см.
  README, раздел «Incident Feedback»
- `EvidenceStore` — обычный SQLite-файл, можно открыть DB Browser for
  SQLite и посмотреть данные руками, если хочется убедиться, что всё
  реально записывается

## Что делать, если у вас уже есть исторические данные

Если у вас уже есть логи агента и инциденты за прошлый период — не
нужно ждать 2 недели. Просто пройдитесь по истории и вызовите
`evaluate_and_log()` для каждого прошлого периода с `timestamp`,
соответствующим реальной дате:

```python
from datetime import datetime, timezone

evaluate_and_log(
    "support-bot-prod", drift_rate_estimate=0.12,
    incidents=[Incident("историческая жалоба из тикет-системы", IncidentSeverity.MINOR)],
    timestamp=datetime(2026, 8, 15, tzinfo=timezone.utc),  # реальная дата из вашей истории
)
```
