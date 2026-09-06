# 🧬 Agenomics

**Genetics for AI Agents. Predictability and compatibility scoring for autonomous agent personalities.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-v0.7.3-orange.svg)](CHANGELOG.md)
[![PyPI](https://img.shields.io/badge/PyPI-agenomics-blue.svg)](https://pypi.org/project/agenomics/)

> **Автор**: Dm.Andreyanov
> **Версия**: 0.7.3
> **Связанные проекты**: [Prizolov Lab](https://prizolov.ru), [Agent Genome Mapping (AGM)](https://github.com/GIBDD-DPS/agent-genome-mapping)
>
> 📐 Формальная спецификация конвейера (Genome → Genome Schema → Phenotype
> → Trust Model → Compatibility Model → Drift Model → Observed Behaviour
> → Evolution/Mutation): [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md).
> Воспроизводимый бенчмарк внутренней согласованности формул, не путайте
> с валидацией против реальных инцидентов: [`benchmark/README.md`](benchmark/README.md).
> 🚀 Хотите подключить реального агента и начать собирать данные для
> Incident Correlation? Гайд на 15 минут: [`docs/CONNECT_YOUR_AGENTS.md`](docs/CONNECT_YOUR_AGENTS.md).
> 🔌 Готовые, проверенные шаблоны для 14 публичных agent-фреймворков
> (LangChain, CrewAI, AutoGen, LlamaIndex и других) с авто-обнаружением и
> запуском по расписанию: [`examples/framework_evaluation/`](examples/framework_evaluation/README.md).
>
> ⚠️ Методология следует **semver 0.x**. До релиза `1.0.0` обратная
> совместимость API не гарантируется между minor-версиями. Между 0.2 и 0.3
> уже менялась сигнатура `TrustScorer()`, добавились параметры.

---

## Что это

**Agenomics**, это методология и open-source инструментарий для оценки предсказуемости личности ИИ-агента и его совместимости с другими агентами в команде, построенные на биологической метафоре генома.

Существующие подходы к доверию к ИИ-агентам обычно строятся на криптографической идентичности, лимитах трат, блокчейн-подписях (см. Agent Passport Standard, AgenticTrust и другие). Agenomics фокусируется на другом вопросе:

> Не «можно ли доверить агенту деньги», а «предсказуемо ли ведёт себя личность агента, и уживётся ли она с другими агентами в команде».

## Ключевая идея

Каждый агент описывается геномом, структурированным набором параметров:

- `cognitive_genes`: как агент мыслит (глубина рассуждений, креативность, риск-толерантность)
- `ethics_genes`: какие ограничения соблюдает (bias threshold, hard constraints)
- `social_genes`: как взаимодействует (стиль общения, разрешение конфликтов)
- `meta_genes`: как эволюционирует (скорость мутации, критерий отбора)

На основе генома вычисляется:

1. **Trust Score** (0-100): итоговая оценка предсказуемости и безопасности агента с учётом критичности домена (Impact Tier) и уровня автономности
2. **Compatibility Score**: насколько хорошо два и более агентов сработаются в одной команде

Полная формула, таблица маппинга поля генома в ось и объяснение шкал: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Быстрый старт

```bash
pip install agenomics
```

```python
from agenomics import TrustScorer, AgentGenome

genome = AgentGenome(
    id="cashflow-predictor-v1",
    domain="finance",
    autonomy="autonomous",  # "advisory" | "autonomous"
    transparency=70,
    bias_control=85,
    data_safety=90,
    drift_rate=0.05,
    has_ledger=True,
)

scorer = TrustScorer()  # или TrustScorer(weight_profile="finance")
result = scorer.score(genome)

print(result.score)             # 0-100
print(result.label)             # Trusted / Conditional / High Risk
print(result.confidence)        # High / Medium / Low, не то же самое, что score
print(result.breakdown)         # разбивка по 5 осям
print(result.capped_reason)     # если применён потолок автономности
print(result.attribution)       # ссылка на методологию и автора
```

Значения `bias_control`, `transparency`, `data_safety` и т.д. должны быть
в диапазоне `[0, 100]`, `drift_rate` в `[0.0, 1.0]`. Значения вне
диапазона вызывают `ValueError` уже на этапе создания `AgentGenome`.

### Мультиязычность (v0.4.3)

```python
from agenomics import TrustScorer, trust_report

result_en = TrustScorer(language="en").score(genome)  # recommendations и capped_reason на английском
print(trust_report(result_en, agent_id="cashflow-predictor-v1", language="en"))
```

Поддерживаются `"ru"` (по умолчанию) и `"en"`, список в `SUPPORTED_LANGUAGES`.
`trust_report_docx()` принимает тот же параметр.

### Настраиваемые профили весов (v0.3)

```python
from agenomics import TrustScorer, TRUST_WEIGHT_PROFILES

print(list(TRUST_WEIGHT_PROFILES.keys()))
# ['default', 'healthcare', 'finance', 'content']

scorer = TrustScorer(weight_profile="healthcare")  # DataSafety весит больше
# или произвольные веса (должны суммироваться в 1.0):
scorer = TrustScorer(weights={"transparency": 0.4, "bias_control": 0.3, "data_safety": 0.1, "predictability": 0.1, "accountability": 0.1})
```

### Compatibility Scorer. Совместимость команды агентов

```python
from agenomics import AgentGenome, CompatibilityScorer

sales_agent = AgentGenome(
    id="recommendation-agent",
    bias_control=80, risk_tolerance=50, social_style=15, has_ledger=False,
)
support_agent = AgentGenome(
    id="support-agent",
    bias_control=82, risk_tolerance=50, social_style=90, has_ledger=True,
)

result = CompatibilityScorer().score_pair(sales_agent, support_agent)
print(result.score)              # 0-100
print(result.breakdown)          # разбивка по 4 осям
print(result.confidence)         # High / Medium / Low
print(result.capped_reason)      # если сработал потолок из-за этического конфликта

# Для команды из 3+ агентов:
team_result = CompatibilityScorer().score_team([sales_agent, support_agent])
print(team_result.average_score)
print(team_result.weakest_pair)  # самое слабое звено команды
```

### Роли агентов (v0.3). Различие не всегда плохо

```python
reviewer = AgentGenome(id="reviewer", role="reviewer", bias_control=85, risk_tolerance=10, social_style=50)
executor = AgentGenome(id="executor", role="executor", bias_control=85, risk_tolerance=90, social_style=50)

result = CompatibilityScorer().score_pair(reviewer, executor)
print(result.complementary_roles)         # True
print(result.breakdown["risk_tolerance"]) # 100.0, разница риск-толерантности не штрафуется,
                                           # это осознанный дизайн (осторожный ревьюер
                                           # при рискованном исполнителе), а не конфликт
```

### Множественный domain. Гибкий Tier

```python
# Агент поддержки, который иногда обрабатывает возвраты денег.
# Tier берётся как максимум (самый строгий) среди всех доменов.
genome = AgentGenome(id="support-refunds", domains=["support", "finance"])
print(genome.tier)  # ImpactTier.TIER_3
```

### Phenotype (v0.5.0). Геном плюс контекст равно выраженные признаки

```python
from agenomics import compute_phenotype, describe_genome_schema

# Одинаковый геном в разном контексте (Tier) даёт разный Phenotype.
# Полная формализация в docs/SPECIFICATION.md
pheno = compute_phenotype(genome)
print(pheno.expressed_traits)  # tier-adjusted значения осей, до весов Trust Model

# Machine-readable описание допустимых полей AgentGenome:
describe_genome_schema()
```

### DriftMonitor v2 (v0.6.0). Точнее обнаруживает деградацию

```python
from agenomics import DriftMonitorV2

monitor = DriftMonitorV2()
for score in [88, 88, 88, 85, 82, 78, 74]:  # слабая, но устойчивая деградация
    monitor.record("support-bot", score)
report = monitor.report("support-bot")
print(report.severity)  # 'mild', 'moderate' и т.д., v1 не обнаруживал такое вовсе
print(report.recovered)  # True, если ранее была тревога, а сейчас её нет
```

### Real-World Evaluation Layer (v0.6.0). Связь Declared Score с реальностью

```python
from agenomics import RealWorldEvaluationLayer, Incident, IncidentSeverity

layer = RealWorldEvaluationLayer(min_observations=10)
layer.record_observation("support-bot", trust_result, incidents=[])
layer.record_observation("support-bot", trust_result_2, incidents=[Incident("...", IncidentSeverity.MODERATE)])
# накопите 10+ реальных наблюдений

report = layer.trust_reality_report("support-bot")
print(report.status)       # "insufficient_data" пока не накоплено достаточно
print(report.correlation)  # реальная, не синтетическая корреляция Declared Score и инцидентов
```

Это первая инфраструктура, делающая метрику **Incident Correlation** из
[`benchmark/`](benchmark/README.md) вычислимой на настоящих данных.
Раньше она была принципиально `not_computable` из-за отсутствия
единой точки сбора.

### Evidence Store (v0.7.0). Персистентность поверх Real-World Evaluation Layer

```python
from agenomics import EvidenceStore, replay_into_evaluation_layer, RealWorldEvaluationLayer

# Записываем наблюдения, они переживают перезапуск процесса (SQLite, stdlib)
store = EvidenceStore("agenomics_evidence.db")
store.record_observation("support-bot", declared_score=85, declared_label="Trusted", genome_hash="abc123")
store.export_json("export.json")  # или export_csv(...)

# После перезапуска процесса, свежий, пустой RealWorldEvaluationLayer:
layer = RealWorldEvaluationLayer(min_observations=10)
replay_into_evaluation_layer(store, layer, "support-bot")  # восстанавливает историю с диска
print(layer.trust_reality_report("support-bot"))
```

`EvidenceStore` не заменяет `RealWorldEvaluationLayer`, а дополняет его
персистентностью, которой ему честно не хватало с v0.6.0. Схема хранения
следует протоколу [`AEP-001`](docs/AEP-001.md).

### Confidence на уровне гена (v0.7.1)

```python
genome = AgentGenome(
    id="x", bias_control=80, data_safety=90,
    axis_confidence={"bias_control": 0.4},  # уверены в data_safety, не уверены в bias_control
)
result = TrustScorer().score(genome)
print(result.axis_confidence)  # {'bias_control': 0.4, 'data_safety': 1.0, ...}
```

Влияет только на `confidence`/`confidence_ratio`, не на сам `score`.

### Per-Axis Drift Monitor (v0.7.1). Какая именно ось деградирует

```python
from agenomics import PerAxisDriftMonitor

monitor = PerAxisDriftMonitor()
for breakdown in history_of_breakdowns:  # список TrustResult.breakdown во времени
    monitor.record("support-bot", breakdown)

print(monitor.weakest_axis("support-bot"))  # например, 'bias_control', а не просто общий score
```

### Team Compatibility Heatmap (v0.7.1)

```python
from agenomics import build_compatibility_matrix, render_heatmap_svg

matrix = build_compatibility_matrix([alice, bob, carol, dave])
print(matrix.weakest_pair)  # например, ('alice', 'dave', 50.0), сразу видно, кто конфликтует
svg = render_heatmap_svg(matrix)  # готовое SVG-изображение
```

### Веб-API

Методология доступна и как HTTP-API: `POST /score` и `POST /compatibility`.
Конфиг для самостоятельного деплоя (например, на Amvera): `amvera.yml`.
Замените `<ваш-адрес-развёртывания>` на реальный адрес после деплоя:

```bash
curl -X POST https://<ваш-адрес-развёртывания>/compatibility \
  -H "Content-Type: application/json" \
  -d '{
        "agents": [
          {"id": "sales", "bias_control": 80, "risk_tolerance": 50, "social_style": 15},
          {"id": "support", "bias_control": 82, "risk_tolerance": 50, "social_style": 90}
        ]
      }'
```

**Для кого:** Команды, которые хотят автоматизировать аудит в CI/CD или дашборде.

## Модули v0.4

Семь дополнительных модулей, расширяющих ядро (Trust Score + Compatibility Score):

### Drift Monitor. Тренд Trust Score во времени

```python
from agenomics import DriftMonitor

monitor = DriftMonitor()
monitor.record("cashflow-bot", score=88)
monitor.record("cashflow-bot", score=75)
monitor.record("cashflow-bot", score=62)
report = monitor.report("cashflow-bot")
print(report.trend, report.alert)  # 'degrading', True
```

### Incident Feedback. Observed Score на основе реальных инцидентов

```python
from agenomics import IncidentFeedback, Incident, IncidentSeverity

feedback = IncidentFeedback()
result = feedback.apply(
    declared_score=88, declared_label="Trusted",
    incidents=[Incident("Слил email клиента", IncidentSeverity.SEVERE)],
)
print(result.observed_score, result.observed_label)  # 63.0, 'Conditional'
```

### Genome Ledger. Хэш-цепочка записей аудита

```python
from agenomics import GenomeLedger

ledger = GenomeLedger()
entry = ledger.record(genome, TrustScorer().score(genome))
print(ledger.verify_integrity())  # True
```

### Genome Matchmaker. Подбор оптимальной команды

```python
from agenomics import GenomeMatchmaker

match = GenomeMatchmaker().best_team(candidates=[alice, bob, carol], roles=["reviewer", "executor"])
print(match.assignment, match.team_result.average_score)
```

### Chain Risk Aggregator. Риск последовательного пайплайна

```python
from agenomics import ChainRiskAggregator

result = ChainRiskAggregator().score_chain([extract_agent, transform_agent, load_agent])
print(result.chain_reliability)  # произведение, не среднее, поэтому ниже, чем ожидалось бы
```

### Prompt-to-Genome Extractor. Автоматическое извлечение генома из промпта

Библиотека не делает сетевых вызовов сама, вы передаёте функцию вызова
своей LLM (Claude, GPT или любой другой):

```python
from agenomics import PromptToGenomeExtractor

def call_my_llm(prompt: str) -> str:
    return my_llm_client.complete(prompt)  # ваша интеграция

extractor = PromptToGenomeExtractor(llm_call=call_my_llm)
genome = extractor.extract(agent_id="support-bot", system_prompt="...")
```

### Reports. Готовые отчёты (Markdown и Word)

```python
from agenomics import trust_report, compatibility_report

print(trust_report(result, agent_id="support-bot"))
```

Для брендированного Word-документа (шапка Prizolov Lab, прогресс-бары по
осям, карточки рекомендаций с «как сделать») установите опциональную
зависимость и используйте `trust_report_docx()`:

```bash
pip install agenomics[docx]
```

```python
from agenomics import trust_report_docx

trust_report_docx(result, agent_id="support-bot", output_path="report.docx")
```

Подробности и ограничения каждого модуля: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Структура репозитория

```
agenomics/
├── agenomics/
│   ├── trust_score.py       # AgentGenome, TrustScorer
│   ├── compatibility.py     # CompatibilityScorer
│   ├── phenotype.py          # Genome Schema, Phenotype (SPECIFICATION.md)
│   ├── evaluation.py          # Real-World Evaluation Layer (v0.6.0)
│   ├── evidence.py             # Evidence Store, персистентность на SQLite, схема AEP-001
│   ├── per_axis_drift.py         # Per-Axis Drift Monitor (v0.7.1)
│   ├── heatmap.py                 # Team Compatibility Heatmap (v0.7.1)
│   ├── drift.py                # Drift Monitor
│   ├── feedback.py              # Incident Feedback Loop
│   ├── ledger.py                  # Genome Ledger
│   ├── matchmaker.py               # Genome Matchmaker
│   ├── chain.py                      # Chain Risk Aggregator
│   ├── extractor.py                   # Prompt-to-Genome Extractor
│   ├── reports.py                      # Markdown/DOCX-отчёты
│   └── api.py                           # веб-API (FastAPI)
├── examples/
│   └── framework_evaluation/  # Автоматический сбор реальных данных с 14 agent-фреймворков
├── benchmark/                # Synthetic Benchmark Suite и Evidence Quality (sensitivity.py),
│                              # репо-инструмент, не входит в pip-пакет, см. benchmark/README.md
├── prompts/                 # системные промпты (Trust Auditor и др.)
├── docs/                     # SPECIFICATION.md, METHODOLOGY.md, AEP-001.md
├── tests/                     # тесты (148+)
├── .github/workflows/          # CI, тесты и smoke-тест запускаются на каждый push/PR
├── amvera.yml                   # конфиг деплоя веб-API на Amvera
├── requirements.txt               # зависимости для запуска репозитория (тесты, FastAPI, uvicorn)
├── pyproject.toml                  # метаданные пакета для PyPI (ядро без внешних зависимостей)
├── CHANGELOG.md                     # история версий
└── CONTRIBUTING.md                   # как предложить изменения
```

### Почему `requirements.txt` и `pyproject.toml` не дублируют друг друга

Это может выглядеть избыточным, поэтому явно: `pyproject.toml` описывает
только сам пакет `agenomics`, который ставится через `pip install agenomics`.
У ядра библиотеки нет внешних зависимостей, кроме стандартной библиотеки
Python. `requirements.txt` нужен для запуска этого репозитория: тестов
(`pytest`) и веб-API (`fastapi`, `uvicorn`), в том числе через
`amvera.yml` и `build.requirementsPath`. Если вы просто ставите пакет
через pip, `requirements.txt` вам не нужен.

## Методология

Полное описание методологии, формула, таблица маппинга поля генома в
ось, объяснение шкал (`social_style`, `risk_tolerance`) и диапазоны
валидации: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Roadmap

- [x] v0.1: формула Trust Score, Tier-множитель, потолок автономности
- [x] v0.1: промпт Trust Auditor (см. `prompts/`)
- [x] v0.2: Compatibility Scorer между несколькими агентами
- [x] v0.2: веб-API (`/score`, `/compatibility`) на Amvera
- [x] v0.2: публикация пакета на PyPI
- [x] v0.3: настраиваемые профили весов (`healthcare`, `finance`, `content`, `safety_critical`)
- [x] v0.3: роли агентов в Compatibility Score (`executor`, `reviewer`)
- [x] v0.3: множественный `domain`, гибкая классификация Tier
- [x] v0.3: Confidence, уверенность в оценке отдельно от score
- [x] v0.3: атрибуция с бэклинком в промпте, коде и API
- [x] v0.3: валидация диапазонов входных данных
- [x] v0.3: CI (GitHub Actions), CHANGELOG.md, CONTRIBUTING.md
- [x] v0.4: Drift Monitor, тренд Trust Score во времени
- [x] v0.4: Incident Feedback Loop, Observed Score на основе реальных инцидентов
- [x] v0.4: Genome Ledger, хэш-цепочка записей аудита
- [x] v0.4: Genome Matchmaker, подбор оптимальной команды
- [x] v0.4: Chain Risk Aggregator, риск последовательного пайплайна агентов
- [x] v0.4: Prompt-to-Genome Extractor с pluggable LLM-клиентом
- [x] v0.4: Reports, отчёты в Markdown
- [x] v0.4.2: how_to, практическая подсказка «как сделать» к каждой рекомендации
- [x] v0.4.2: trust_report_docx(), брендированный Word-отчёт (опционально python-docx)
- [x] v0.4.3: мультиязычность (`language="ru"|"en"` в Scorer'ах и report-функциях)
- [x] v0.4.3: инструкция определения языка в промпте Trust Auditor
- [x] v0.5.0: **AGENOMICS SPECIFICATION v1.0** (`docs/SPECIFICATION.md`), формальный конвейер Genome → Genome Schema → Phenotype → Trust Model → Compatibility Model → Drift Model → Observed Behaviour → Evolution/Mutation
- [x] v0.5.0: Genome Schema и Phenotype как реализованные, тестируемые понятия (`agenomics/phenotype.py`)
- [x] v0.5.0: **Synthetic Benchmark Suite** (`benchmark/`), 5 вычислимых метрик и честный `not_computable` для Incident Correlation
- [x] v0.6.0: **DriftMonitorV2** (rolling window, EWMA, волатильность, severity, recovery detection), исправляет находку бенчмарка v0.1: mild-деградация не обнаруживалась
- [x] v0.6.0: Compatibility Accuracy v2, 270 систематических случаев в 9 категориях вместо 4 ручных
- [x] v0.6.0: **RealWorldEvaluationLayer**, инфраструктура для реальной, не синтетической Incident Correlation на production-данных
- [x] v0.6.0: `benchmark/BENCHMARKS.md`, зафиксированные, воспроизводимые числа
- [x] v0.6.1: **Evidence Quality**: Weight Sensitivity, Threshold Sensitivity, Bootstrap 95% CI (`benchmark/sensitivity.py`), устойчивость метрик, не новый функционал
- [x] v0.7.0: **Evidence Store** (`agenomics/evidence.py`), персистентное хранилище наблюдений и инцидентов с provenance, JSON/CSV экспорт, `replay_into_evaluation_layer()`
- [x] v0.7.0: CI прогоняет `benchmark.run_benchmark` отдельным шагом
- [x] v0.7.0: [`docs/CONNECT_YOUR_AGENTS.md`](docs/CONNECT_YOUR_AGENTS.md), практический гайд подключения реальных агентов за 15 минут
- [x] v0.7.1: **[AEP-001](docs/AEP-001.md)**, Agenomics Evidence Protocol v1.0, формальная схема Observation/Incident/Provenance с обязательным правилом Privacy
- [x] v0.7.1: Confidence на уровне гена (`AgentGenome.axis_confidence`)
- [x] v0.7.1: `PerAxisDriftMonitor`, дрейф каждой оси Trust Score отдельно
- [x] v0.7.1: Team Compatibility Heatmap (`agenomics/heatmap.py`)
- [x] v0.7.1: [`docs/PRIZOLOV_BRIDGE_INTERFACE.md`](docs/PRIZOLOV_BRIDGE_INTERFACE.md), честный интерфейс-контракт для внешних интеграций
- [x] v0.7.2: **`examples/framework_evaluation/`**, автоматический сбор реальных наблюдений с 14 публичных agent-фреймворков (LangChain, CrewAI, AutoGen/AG2, LlamaIndex, Semantic Kernel, LangGraph, Haystack, CAMEL-AI, OpenAI Agents SDK, Griptape и другие), с авто-обнаружением новых фреймворков и запуском по расписанию через GitHub Actions
- [x] v0.7.2: `EvidenceStore` получил `execution_status` и `duration_seconds`. Исправляет баг: история для `predictability` хранилась только в памяти процесса и терялась между запусками CI
- [x] v0.7.2: `has_ledger` больше не выставляется в `True` только потому, что лог агента был захвачен. Честный дефолт `False`, явный параметр для подтверждённых случаев
- [x] v0.7.2: Framework Evaluation smoke-тест в основном CI, 12 тестов на механику пайплайна без установки всех 14 реальных библиотек
- [x] v0.7.3: исправлена миграция схемы `EvidenceStore` — файлы базы со старой схемой (например, восстановленные из кэша GitHub Actions) теперь получают недостающие колонки автоматически, а не падают с `sqlite3.OperationalError`
- [ ] v0.8: Evolution/Mutation как предложение, требующее подтверждения человеком, не реализовано даже как прототип
- [ ] v0.8: реальная Incident Correlation на настоящих production-данных, накопленных через EvidenceStore
- [ ] v0.8: формальный Evaluation Protocol (EP-001..EP-00N с input, ground truth, metric, threshold, CI на каждый)
- [ ] v0.8: предиктивная валидность (Trust Score(t) → вероятность инцидента в будущем, ROC-AUC, Brier Score)
- [ ] v0.8: веб-калькулятор на prizolov.ru
- [ ] v0.8: Genome Ledger как публичный сервис, сейчас только локальный in-memory прототип
- [ ] v0.8: мультиязычность за пределами ru/en

Полная история изменений: [`CHANGELOG.md`](CHANGELOG.md).

## Тесты и CI

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -v
```

Тесты автоматически запускаются на каждый push/PR через GitHub Actions
(см. `.github/workflows/`).

## Contributing

См. [`CONTRIBUTING.md`](CONTRIBUTING.md). Обратная связь и предложения
через GitHub Issues.

## Лицензия

Apache 2.0, см. [LICENSE](LICENSE).

---

© 2026 Dm.Andreyanov. Agenomics, независимый проект, развивающий идеи Agent Genome Mapping™ (Prizolov Lab).
