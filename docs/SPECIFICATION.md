# AGENOMICS SPECIFICATION v1.0

**Автор**: Dm.Andreyanov · **Проект**: Prizolov Lab
**Проверено на реализации**: agenomics v0.7.0

> Версионирование спецификации отделено от версионирования кода:
> спецификация может оставаться v1.0 через несколько minor-релизов
> кода, если формальные понятия не меняются, только их реализация.

## 0. Статус документа

Это формализация того, что уже реализовано в коде (не проектная
декларация несуществующего). Каждое понятие ниже указывает на
конкретный модуль/класс/функцию — если ссылки нет, понятие помечено
как **не реализовано** явно, а не тихо подразумевается.

## 1. Конвейер (Pipeline)

```
Agent Genome
    ↓
Genome Schema        (валидация формы и диапазонов)
    ↓
Phenotype            (геном + контекст = выраженные признаки)
    ↓
Trust Model          (веса + потолки → Trust Score)
    ↓
Compatibility Model  (пары/команды → Compatibility Score)
    ↓
Drift Model          (история во времени → тренд, алерт)
    ↓
Observed Behaviour   (реальные инциденты → Observed Score)
    ↓
Evolution / Mutation (обратная связь → корректировка генома)
```

Каждый уровень — это отдельный, тестируемый шаг. Не все уровни имеют
одинаковую зрелость реализации — это явно указано в каждом разделе.

---

## 2. Agent Genome

**Реализация**: `agenomics.AgentGenome` (`trust_score.py`)

Декларативное описание агента — «генотип»: то, что заявлено о нём при
создании (кем угодно — вручную, через `PromptToGenomeExtractor`, через
конфиг). Сам по себе Genome не содержит логики оценки, только данные.

```python
AgentGenome(
    id="support-bot",
    domain="support",
    autonomy="autonomous",
    transparency=85, bias_control=72, data_safety=90,
    drift_rate=0.35, has_ledger=False,
)
```

## 3. Genome Schema

**Реализация**: `agenomics.phenotype.GENOME_SCHEMA`, `describe_genome_schema()`

Формальный контракт: какие поля существуют, какого типа, в каком
диапазоне, обязательны ли. Валидация диапазонов физически применяется
в `AgentGenome.__post_init__()` (`ValueError` при выходе за границы) —
Genome Schema делает эти правила **машиночитаемыми и интроспектируемыми**
отдельно от кода валидации, для документации, автогенерации форм,
внешних инструментов.

```python
from agenomics.phenotype import describe_genome_schema
describe_genome_schema()
# [{"name": "bias_control", "type": "float | null", "required": False,
#   "range": (0, 100), "description": "Ось Trust Model / Compatibility Model (этика)"}, ...]
```

**Гарантия согласованности**: `tests/test_phenotype.py::test_genome_schema_covers_all_dataclass_fields`
проверяет, что схема не расходится с реальными полями `AgentGenome` —
без этого теста документация могла бы незаметно устареть относительно кода.

## 4. Phenotype

**Реализация**: `agenomics.phenotype.compute_phenotype()`

Ключевое понятие, которого не было явно до v0.5. Формализует различие
между **декларируемым геномом** (сырые значения) и **выраженными
признаками в конкретном контексте** (после tier-множителя, но ещё до
весов и меток Trust Model).

Биологическая аналогия в явном виде: одинаковый генотип в разной среде
даёт разный фенотип. Здесь «среда» — это Impact Tier (домен агента).

```python
from agenomics.phenotype import compute_phenotype

# Одинаковый Genome...
kwargs = dict(id="x", transparency=80, bias_control=80, data_safety=80, drift_rate=0.15)
genome_tier1 = AgentGenome(**kwargs, tier_override=ImpactTier.TIER_1)
genome_tier3 = AgentGenome(**kwargs, tier_override=ImpactTier.TIER_3)

# ...даёт РАЗНЫЙ Phenotype:
compute_phenotype(genome_tier1).expressed_traits["accountability"]  # 30.0
compute_phenotype(genome_tier3).expressed_traits["accountability"]  # 9.0
```

Доказано тестом `tests/test_phenotype.py::test_same_genome_different_tier_gives_different_phenotype`.

## 5. Trust Model

**Реализация**: `agenomics.TrustScorer`

Берёт Phenotype (концептуально) и применяет веса (`weight_profile`),
потолок автономности, формирует итоговый `TrustResult`: `score`, `label`,
`confidence`, `recommendations`, `how_to`. Формула и её ограничения —
`docs/METHODOLOGY.md`, разделы 3, 7.

Настраиваемые профили весов (`default`/`healthcare`/`finance`/`content`)
— это формально разные калибровки одной и той же Trust Model, не разные
модели.

## 6. Compatibility Model

**Реализация**: `agenomics.CompatibilityScorer`

Отдельная модель (не производная от Trust Model), оперирующая парой/
командой геномов вместо одного. Формула, роли, профили весов —
`docs/METHODOLOGY.md`, разделы 5, 8.4.

## 7. Drift Model

**Реализация**: `agenomics.DriftMonitor` (v1), `agenomics.DriftMonitorV2` (v0.6.0)

Единственная модель в конвейере, оперирующая **историей во времени**,
а не одним снимком. Вход — последовательность `TrustResult.score` для
одного `agent_id`; выход — тренд/тяжесть и алерт.

`DriftMonitor` (v1) — простая линейная эвристика (первый снимок vs
последний). Ограничение, найденное бенчмарком (`benchmark/BENCHMARKS.md`):
не обнаруживала слабую (mild) деградацию за разумное окно наблюдения.

`DriftMonitorV2` (v0.6.0) — rolling window + EWMA + волатильность +
явная классификация тяжести (`none`/`mild`/`moderate`/`severe`/`sudden`/
`volatile`) + обнаружение восстановления (`recovered`). Откалибрована
на 7 синтетических сценариях (`benchmark/scenarios.py::DRIFT_SCENARIOS_V2`).
Честный остаточный дефект: первые ~2 снимка колебательного паттерна (до
заполнения rolling window) могут классифицироваться неточно — известный
transient, не устранённый полностью.

## 8. Observed Behaviour

**Реализация**: `agenomics.Incident`, `agenomics.IncidentFeedback`, `agenomics.GenomeLedger`, `agenomics.RealWorldEvaluationLayer` (v0.6.0), `agenomics.EvidenceStore` (v0.7.0)

Единственный уровень конвейера, где в систему попадают **данные из
реального мира**, а не производные от Genome. `IncidentFeedback`
пересчитывает декларативный Trust Score в "наблюдаемый" на основе
подтверждённых инцидентов; `GenomeLedger` — append-only журнал того,
что было заявлено и оценено, с хэш-цепочкой целостности.

**`RealWorldEvaluationLayer` (v0.6.0)** — связующая инфраструктура:
собирает Declared Score + реальные инциденты + дрейф для агента во
времени в одном месте и, когда накоплено достаточно наблюдений
(`min_observations`), считает `TrustRealityReport` с реальной (не
синтетической) корреляцией между Declared Score и нагрузкой инцидентов.

**`EvidenceStore` (v0.7.0)** — закрывает ограничение, которое честно
признавалось с v0.6.0: `RealWorldEvaluationLayer` сам по себе in-memory
и не переживает перезапуск процесса. `EvidenceStore` — персистентное
(SQLite, часть стандартной библиотеки — без новых внешних зависимостей)
хранилище наблюдений и инцидентов с provenance-полями (`genome_hash`,
`agenomics_version`, `timestamp`). Экспортирует в JSON/CSV. Функция
`replay_into_evaluation_layer()` воспроизводит сохранённые наблюдения
обратно в свежий `RealWorldEvaluationLayer` — то есть цикл «записать →
перезапустить процесс → загрузить обратно → посчитать корреляцию»
теперь реально работает, а не только теоретически возможен.

**Текущая зрелость**: `EvidenceStore` — первый компонент уровня
Observed Behaviour, который персистентен. Остальные компоненты
(`RealWorldEvaluationLayer`, `DriftMonitorV2`) всё ещё in-memory —
`EvidenceStore` дополняет их, а не заменяет их внутреннюю логику.
Именно отсутствие накопленных за реальный период эксплуатации данных —
а не отсутствие инфраструктуры для их хранения — причина, по которой
`benchmark.measure_incident_correlation()` по-прежнему честно
возвращает `not_computable`: технически собрать такие данные теперь
можно, но пока никто не собрал.

## 9. Evolution / Mutation

**Статус: НЕ РЕАЛИЗОВАНО.** Указано в спецификации как логическое
замыкание конвейера (Observed Behaviour → корректировка Genome), но
кода, реализующего это, не существует ни в каком виде — ни прототипа,
ни заглушки.

Ближайшее, что есть в кодовой базе и концептуально соседствует с этой
идеей — `meta_genes` в описании методологии (`README.md`, раздел
"Ключевая идея": "скорость мутации, критерий отбора") и параметр
`GenomeMatchmaker`, подбирающий назначение ролей — но ни то, ни другое
не меняет сам Genome со временем на основе Observed Behaviour.

Концептуально ожидаемая форма (без обязательств по срокам реализации):
по мере накопления `Incident`-записей в `GenomeLedger` для конкретного
`agent_id`, система могла бы предлагать (не применять автоматически)
скорректированные значения полей Genome — например, снижать заявленный
`bias_control`, если инциденты систематически указывают на ось `ethics`.
Это открытый пункт v0.8+, не более.

---

## 10. Как это соотносится с Benchmark Suite

Каждый уровень конвейера, для которого возможна синтетическая проверка
внутренней согласованности, покрыт в `benchmark/` (см. `benchmark/README.md`):

| Уровень конвейера | Метрика бенчмарка |
|---|---|
| Genome Schema | `tests/test_phenotype.py` (согласованность схемы и кода) |
| Phenotype | `tests/test_phenotype.py` (генотип→разный фенотип по контексту) |
| Trust Model | Reproducibility, Trust Calibration (formula consistency) |
| Compatibility Model | Compatibility Accuracy v2 (n=270, 9 категорий) |
| Drift Model | Drift Detection Lag (v1) / Drift Detection v2 (7 сценариев, `DriftMonitorV2`) |
| Observed Behaviour | Incident Correlation — честно `not_computable` синтетически; инфраструктура для реального вычисления — `RealWorldEvaluationLayer` + `EvidenceStore` (персистентность) |
| Evolution / Mutation | Не применимо — уровень не реализован |

## 11. Версионирование спецификации

- **v1.0** (этот документ) — проверено на коде v0.7.0. Формализует
  уровни 1-6 (Genome → Compatibility Model) как реализованные и
  протестированные, 7 (Drift Model) и часть 8 (Observed Behaviour:
  `IncidentFeedback`, `GenomeLedger`, `RealWorldEvaluationLayer`) —
  реализованными, но in-memory; `EvidenceStore` (тоже уровень 8) —
  первый персистентный компонент этого уровня. 9 (Evolution/Mutation)
  — нереализованным.
- Изменение состава уровней конвейера (не их реализации) потребует
  бампа до v2.0. Улучшение реализации существующего уровня (например,
  добавление персистентности Drift Model) не требует бампа спецификации.
