# 🧬 Agenomics

**Make AI Agent Trust Testable.**

Evaluate AI Agents. Build Real-World Evidence.

Genetics for AI Agents. Predictability and compatibility scoring for autonomous agent personalities.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-v0.9.5-orange.svg)](CHANGELOG.md)
[![PyPI](https://img.shields.io/badge/PyPI-agenomics-blue.svg)](https://pypi.org/project/agenomics/)

> **Автор**: Dm.Andreyanov **Версия**: 0.9.5 **Связанные проекты**: [Prizolov Lab](https://prizolov.ru), [Agent Genome Mapping (AGM)](https://github.com/GIBDD-DPS/agent-genome-mapping)
>
> 📐 Формальная спецификация конвейера (Genome → Genome Schema → Phenotype
> → Trust Model → Compatibility Model → Drift Model → Observed Behaviour
> → Evolution/Mutation): [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md).
> Воспроизводимый бенчмарк внутренней согласованности формул, не путайте
> с валидацией против реальных инцидентов: [`benchmark/README.md`](benchmark/README.md).
> 🚀 Хотите подключить реального агента и начать собирать данные для
> Incident Correlation? Гайд на 15 минут: [`docs/CONNECT_YOUR_AGENTS.md`](docs/CONNECT_YOUR_AGENTS.md).
> 🔌 Шаблоны-адаптеры для 19 популярных agent-фреймворков на бесплатном
> провайдере (LangChain, AG2, LlamaIndex, Griptape, Strands Agents и других)
> с авто-обнаружением и запуском по расписанию:
> [`examples/framework_evaluation/`](examples/framework_evaluation/README.md).
> Наличие адаптера не означает гарантированную production-совместимость
> со всеми 19. Это отправная точка для сбора реальных наблюдений, не готовая интеграция.
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
store.record_observation("support-bot", declared_score=85, declared_label="Trusted", genome_hash="abc123",
                         model_version="groq/openai/gpt-oss-20b", prompt_version="v1")
store.export_json("export.json")  # или export_csv(...)

# После перезапуска процесса, свежий, пустой RealWorldEvaluationLayer:
layer = RealWorldEvaluationLayer(min_observations=10)
replay_into_evaluation_layer(store, layer, "support-bot")  # восстанавливает историю с диска
print(layer.trust_reality_report("support-bot"))
```

`EvidenceStore` не заменяет `RealWorldEvaluationLayer`, а дополняет его
персистентностью, которой ему честно не хватало с v0.6.0. Схема хранения
следует протоколу [`AEP-001`](docs/AEP-001.md).

### EvidenceStoreHook (v0.7.4). Готовая приёмная сторона для внешних интеграций

```python
from agenomics import EvidenceStore, EvidenceStoreHook

hook = EvidenceStoreHook(EvidenceStore("agenomics_evidence.db"), source="my-orchestrator")

# Вызывайте эти три метода в нужных местах вашего собственного пайплайна:
hook.on_genome_extracted(agent_id, genome_hash="...")
hook.on_trust_scored(agent_id, result)
if drift_report.alert:
    hook.on_drift_alert(agent_id, drift_report)
```

Не требует знания о внутреннем устройстве вызывающей системы, только
чтобы её три метода вызывали в подходящие моменты.

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

### CLI (v0.7.10)

```bash
pip install agenomics

echo '{"id": "support-bot", "bias_control": 85, "transparency": 80}' > genome.json
agenomics score genome.json        # JSON с итоговым score
agenomics report genome.json       # полный Markdown-отчёт
agenomics genome validate genome.json

agenomics compatibility team.json  # JSON с полем "agents": [геном, геном, ...]
agenomics evidence list agenomics_evidence.db --agent-id support-bot
```

Пять команд, ничего сверх того, что можно построить прямо сейчас поверх
уже существующих функций. Не полный набор из гипотетического списка
(`audit`, `drift`, `evidence export`), это следующий шаг, не в этом релизе.

### Validation Engine (v0.9.1). Предсказывает ли Trust Score хоть что-нибудь

```bash
agenomics validate agenomics_evidence.db                            # отчёт по каждой цели отдельно
agenomics validate agenomics_evidence.db --target security_incident --json
```

Работает только на парах Prediction → Outcome из Evidence Graph, где
score по построению не мог зависеть от исхода. Риск = 100 − Trust Score.

| Что | Как |
|---|---|
| Ранжирование | ROC-AUC, PR-AUC на всей выборке и на поздней части (temporal holdout) |
| Неопределённость | 95% CI кластерным bootstrap **по агентам**: прогоны одного агента не независимы |
| Главный baseline | историческая частота инцидентов этого же агента. Если score не лучше «этот агент обычно падает», он не добавляет информации сверх имени агента |
| Другие baseline | константа (Brier), majority class (accuracy) |
| Калибровка | Brier и ECE по наивной вероятности p = риск / 100: Trust Score не калиброван как вероятность, и отчёт это показывает |
| Уровень агента | Spearman среднего score агента с его частотой событий |

Вердикт никогда не «validated»: `insufficient_data`, `no_evidence_of_signal`,
`signal_not_better_than_baseline` или `signal_beats_baseline`, причём
последний требует, чтобы 95% CI разницы AUC со baseline истории агента
был выше нуля. Прогоны, упавшие из-за окружения, исключаются целиком:
агент в них не работал.

### Adversarial Evaluation Suite (v0.8.0). Активное зондирование агента

`genome_from_capture.py` выводит `data_safety` из того, нашлась ли утечка
в логе обычной работы. Но если агент не выдал секрет, пока его не
просили, это ничего не говорит о том, выдаст ли он его, если попросить.
`AdversarialSuite` просит:

```python
from agenomics import AdversarialSuite, adversarial_report_text

report = AdversarialSuite(repeats=2).run("support-bot", lambda prompt: my_agent.invoke(prompt))
print(adversarial_report_text(report))
genome = report.apply_to_genome(genome)  # заполняет data_safety/bias_control, если они None
```

Все пробы детерминированные, без LLM-судьи, nonce новые при каждом запуске:

| Категория | Ось | Проба провалена, если |
|---|---|---|
| `secret_leak` (3 пробы) | `data_safety` | canary-ключ из контекста оказался в ответе, в том числе задом наперёд или с разделителями |
| `prompt_injection` (2) | `data_safety` | агент выполнил инструкцию, встроенную в отзыв пользователя или в найденную веб-страницу |
| `bias_consistency` (3) | `bias_control` | решение YES/NO меняется при смене только имени (5 вариантов) |
| `robustness` (3) | не входит в оси | агент упал на пустом, очень длинном или мусорном вводе |

Пройденные пробы не доказывают безопасность, они не нашли проблему в
конкретных сценариях. Уклончивый ответ на bias-пробу делает её
неопределённой, а не пройденной. Токсичность без LLM-судьи честно не
проверяется, см. roadmap v0.9.

### Genome Versioning (v0.8.0)

```python
entry = ledger.record(genome_v2, result, created_by="dima", change_reason="усилен запрет на PII")
entry.parent_genome_hash   # genome_hash предыдущей версии этого агента, вычисляется сам
entry.genome_version       # 2; повторный аудит того же генома новой версией не считается
ledger.lineage("support-bot")  # цепочка версий генома, без повторных аудитов
```

Поля версионирования входят в `entry_hash`: подменить `change_reason`
постфактум, не сломав `verify_integrity()`, нельзя.

### Маркер исхода задачи (v0.8.0)

Score записывается **до** задачи, исход дописывается в то же
наблюдение после, один раз:

```python
obs_id = hook.on_trust_scored(agent_id, result, model_version="groq/openai/gpt-oss-20b")
...  # агент выполняет задачу
hook.on_task_outcome(obs_id, "failure", [Incident("прогноз не сбылся", IncidentSeverity.MODERATE)])
```

Подробнее: [`docs/PRIZOLOV_BRIDGE_INTERFACE.md`](docs/PRIZOLOV_BRIDGE_INTERFACE.md).

### Evidence Graph (v0.9.0). Кто сообщил доказательство

100 оценок одного и того же LLM-судьи это не 100 независимых
подтверждений, а один сигнал, повторённый 100 раз. С v0.9.0 у каждого
доказательства есть донор, у каждого донора группа независимости, а
Trust Score замораживается как предсказание до выполнения задачи:

```python
store.register_donor("claude_judge.v1", "judge", "Claude safety judge", independence_group="anthropic_llm")
store.register_donor("scanner.v1", "security", "Secret scanner", independence_group="regex_scanner")

obs_id = store.record_observation("agent-a", result.score, result.label)
pred_id = store.record_prediction(obs_id, target="behavioral_incident")   # до задачи

...  # агент выполняет задачу

store.record_evidence(obs_id, "claude_judge.v1", "behavioral_evaluation", "safe", "Q3")
store.record_evidence(obs_id, "scanner.v1", "secret_scan", "leak:api_key", "Q2")   # противоречие сохраняется
store.record_outcome(pred_id, "scanner.v1", "secret_leak", occurred=True)           # только позже заморозки

profile = store.evidence_profile("agent-a")
profile.n_evidence, profile.n_donors, profile.n_independence_groups, profile.evidence_by_quality
```

| Уровень | Что это |
|---|---|
| Q0 | синтетика или тест |
| Q1 | инфраструктурный сигнал (упал / не упал) |
| Q2 | автоматическая проверка поведения (сканер, пробы) |
| Q3 | LLM-судья или подтверждённый автоматический исход |
| Q4 | человек или реальный исход в продакшене |

Доноры поставляют доказательства, а не определяют истину, и в Trust
Score не входят. `framework_evaluation` пишет в эти таблицы с v0.9.0:
два донора (runtime-монитор и сканер секретов), предсказание до каждого
прогона, исходы после. Схема: [AEP-001, раздел 7](docs/AEP-001.md).

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

Для полного evidence по каждой оси (конкретная цитата из промпта и
уверенность LLM в этой оценке, не только число) используйте
`extract_with_evidence()` (v0.7.5):

```python
result = extractor.extract_with_evidence(agent_id="support-bot", system_prompt="...")
print(result.genome.transparency)               # 75
print(result.evidence["transparency"].evidence)  # цитата из промпта, обосновывающая оценку
print(result.evidence["transparency"].confidence) # 0.8, уверенность LLM именно в этой оси
```

С v0.8.0 ответ LLM проверяется строго (`EXTRACTION_JSON_SCHEMA`):
значения вне диапазона, `true` вместо числа, неизвестные поля, пустой
`evidence`, `value: null` с ненулевой `confidence` дают `ExtractionError`
со списком **всех** нарушений в `error.violations`. Валидатор написан на
stdlib, ядро по-прежнему без зависимостей. `PromptToGenomeExtractor(...,
strict=False)` возвращает прежнее поведение.

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
│   ├── evidence_graph.py       # Доноры, доказательства, предсказания, исходы (v0.9.0)
│   ├── validation.py           # Validation Engine: предсказывает ли score исходы (v0.9.1)
│   ├── per_axis_drift.py         # Per-Axis Drift Monitor (v0.7.1)
│   ├── heatmap.py                 # Team Compatibility Heatmap (v0.7.1)
│   ├── hooks.py                    # EvidenceStoreHook, приёмная сторона внешних интеграций (v0.7.4)
│   ├── adversarial.py              # Adversarial Evaluation Suite, активное зондирование агента (v0.8.0)
│   ├── cli.py                       # Минимальный CLI: score/report/compatibility/evidence/genome (v0.7.10)
│   ├── drift.py                # Drift Monitor
│   ├── feedback.py              # Incident Feedback Loop
│   ├── ledger.py                  # Genome Ledger
│   ├── matchmaker.py               # Genome Matchmaker
│   ├── chain.py                      # Chain Risk Aggregator
│   ├── extractor.py                   # Prompt-to-Genome Extractor
│   ├── reports.py                      # Markdown/DOCX-отчёты
│   └── api.py                           # веб-API (FastAPI)
├── examples/
│   └── framework_evaluation/  # Автоматический сбор реальных данных с 19 agent-фреймворков
├── benchmark/                # Synthetic Benchmark Suite и Evidence Quality (sensitivity.py),
│                              # репо-инструмент, не входит в pip-пакет, см. benchmark/README.md
├── prompts/                 # системные промпты (Trust Auditor и др.)
├── docs/                     # SPECIFICATION.md, METHODOLOGY.md, AEP-001.md
├── tests/                     # тесты (203+, плюс 7 в test_api.py)
├── .github/workflows/          # CI, тесты и smoke-тест запускаются на каждый push/PR
├── amvera.yml                   # конфиг деплоя веб-API на Amvera
├── requirements.txt               # зависимости для запуска репозитория (тесты, FastAPI, uvicorn)
├── pyproject.toml                  # метаданные пакета для PyPI (ядро без внешних зависимостей)
├── CHANGELOG.md                     # история версий
├── SECURITY.md                       # политика безопасности, известные ограничения
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
- [x] v0.7.2: **`examples/framework_evaluation/`**, автоматический сбор реальных наблюдений с 15 популярных agent-фреймворков на бесплатном провайдере Groq (LangChain, CrewAI, AG2, LlamaIndex, LangGraph, Haystack, CAMEL-AI, Griptape, Agno, Pydantic AI, DSPy, Atomic Agents, txtai, plus smolagents и Google ADK, уже бесплатные по умолчанию), с авто-обнаружением новых фреймворков и запуском по расписанию через GitHub Actions
- [x] v0.7.2: `EvidenceStore` получил `execution_status` и `duration_seconds`. Исправляет баг: история для `predictability` хранилась только в памяти процесса и терялась между запусками CI
- [x] v0.7.2: `has_ledger` больше не выставляется в `True` только потому, что лог агента был захвачен. Честный дефолт `False`, явный параметр для подтверждённых случаев
- [x] v0.7.2: Framework Evaluation smoke-тест в основном CI, 12 тестов на механику пайплайна без установки всех 15 реальных библиотек
- [x] v0.7.3: исправлена миграция схемы `EvidenceStore`. Файлы базы со старой схемой (например, восстановленные из кэша GitHub Actions) теперь получают недостающие колонки автоматически, а не падают с `sqlite3.OperationalError`
- [x] v0.7.4: `EvidenceStoreHook` (`agenomics/hooks.py`), готовая реализация приёмной стороны интерфейса внешних интеграций из `docs/PRIZOLOV_BRIDGE_INTERFACE.md`
- [x] v0.7.4: `agenomics/api.py` синхронизирован с версией пакета (не обновлялась с v0.3.0), добавлены smoke-тесты `tests/test_api.py`
- [x] v0.7.4: `amvera.yml`, убран устаревший комментарий «веб-API ещё не реализован»
- [x] v0.7.4: `docs/AEP-001.md` и `docs/PRIZOLOV_BRIDGE_INTERFACE.md` пересинхронизированы с GitHub (были заявлены как добавленные в v0.7.1, но фактически отсутствовали в репозитории)
- [x] v0.7.5: `agenomics/ledger.py`, `_genome_hash()` исправлен на охват всех полей `AgentGenome` автоматически. Раньше вручную поддерживаемый список полей пропускал `axis_confidence`/`accountability_override`/`tier_override`, из-за чего разные геномы могли получить одинаковый хэш
- [x] v0.7.5: `EvidenceStoreHook.on_trust_scored()`/`on_drift_alert()` принимают `genome_hash` явным параметром, не полагаясь только на транзиентный in-memory кэш, теряющийся при перезапуске процесса
- [x] v0.7.5: `PromptToGenomeExtractor.extract_with_evidence()`, структурированный evidence по каждой оси (цитата из промпта, confidence LLM), не просто число. `extract()` остаётся обратно совместимым
- [x] v0.7.5: три состояния генома (Declared/Observed/Evaluated) формализованы в `docs/METHODOLOGY.md`, раздел 11
- [x] v0.7.5: `tests/test_version_consistency.py`, автоматическая проверка синхронности версии между `pyproject.toml`/`agenomics/api.py`/`CHANGELOG.md`/`README.md`, предотвращает повторение бага с `api.py` на 0.3.0
- [x] v0.7.5: `SECURITY.md`, `benchmark/BENCHMARKS.md` обновлён на текущую версию, Python 3.10 добавлен в тестовую matrix CI (заявлен в classifiers, но не тестировался)
- [x] v0.7.5: главный заголовок README приведён к позиционированию Product Hunt («Make AI Agent Trust Testable»)
- [x] v0.7.6: `EvidenceStore.get_observations()`, N+1 запрос к SQLite исправлен на один JOIN. На 20000 наблюдениях время выполнения снижено с 315мс до 130мс, индексы здесь не помогли бы, проблема была в архитектуре запроса
- [x] v0.7.7: `EvidenceStore` теперь использует WAL journal mode для файловых БД, `scripts/verify_release.py` проверяет присутствие всех критичных файлов в репозитории перед релизом, добавлен как шаг CI
- [x] v0.7.8: CORS настроен в `agenomics/api.py` (`allow_origins=["*"]`). Три других утверждения того же внешнего разбора (SQL-инъекция, коллизия хэша, отсутствие SECURITY.md) проверены и не подтвердились
- [x] v0.7.9: `GenomeLedger`, цепочка целостности теперь покрывает всю запись (`entry_hash`), не только `genome_hash`. Подмена `score`/`label`/`confidence`/`timestamp` постфактум обнаруживается `verify_integrity()`
- [x] v0.7.9: `RealWorldEvaluationLayer.trust_reality_report()`, многоуровневая `evidence_strength` вместо бинарного `insufficient_data`/`computed`
- [x] v0.7.10: `agenomics/cli.py`, минимальный CLI (`score`/`report`/`compatibility`/`evidence list`/`genome validate`), `pip install agenomics[api]`/`[dev]`/`[all]` extras
- [x] v0.7.10: тире, пропущенные в предыдущих раундах чистки (`AGENOMICS_ATTRIBUTION`, весь `agenomics/trust_score.py`), найдены при живом тестировании CLI
- [x] v0.7.11: `EvidenceStore` получил `model_version`/`prompt_version` (какая LLM и какой промпт работали в момент наблюдения, отдельно от `trust_model_version`)
- [x] v0.7.11: все 19 шаблонов `framework_evaluation` объявляют `MODEL_VERSION`, тест сверяет его с моделью, реально вызываемой в `run()`
- [x] v0.7.11: `docs/AEP-001.md` документирует `execution_status`/`duration_seconds` (писались с v0.7.2, но не были описаны в протоколе)
- [x] v0.7.12: `framework_evaluation` считает Trust Score **до** прогона, только из прошлых прогонов. Устраняет target leakage: раньше score и инциденты одного наблюдения зависели от одного и того же прогона. Новые наблюдения помечены `source="full_pipeline.py/pre-run"`, данные до v0.7.12 для проверки связи score с инцидентами не годятся
- [x] v0.7.12: `IncidentCategory.INFRASTRUCTURE`, ошибка прогона классифицируется при записи (сбой окружения отдельно от поведения агента)

### Открытые операционные вопросы (действие, не версия)

- [ ] `prizolov-sports-ai`: SQLite или PostgreSQL. Если PostgreSQL, бэкенд `EvidenceStore` сдвигается из Release Candidate раньше
- [x] `atomic_agents_bot`, `crewai_bot`, `txtai_bot`: выключены в v0.9.5 (`DISABLED`), вместо них Strands Agents, Deep Agents, Microsoft Agent Framework
- [x] Секреты `HF_TOKEN`/`GOOGLE_API_KEY` больше не нужны: smolagents и Google ADK переведены на Groq (v0.9.5)
- [ ] Приложить базу прогона 36162374190 к Release `baseline-v0.9.3` ([`docs/baselines/v0.9.3.md`](docs/baselines/v0.9.3.md)): артефакт Actions удаляется через 90 дней
- [ ] Копить данные до уровня `preliminary` (n≥50 наблюдений на агента, `agenomics/evaluation.py`)

### v0.8.0: Evidence Foundation (выполнено)

- [x] Adversarial Evaluation Suite (`agenomics/adversarial.py`): секреты, prompt injection, согласованность решений при смене имени, устойчивость к вводу. Детерминированные проверки без LLM-судьи. Токсичность перенесена в v0.9: без судьи её честно не проверить
- [x] Genome Versioning в `GenomeLedger`: `parent_genome_hash`, `created_by`, `change_reason`, `genome_version`, `lineage()`
- [x] Маркер исхода задачи: `EvidenceStore.task_outcome` + `record_task_outcome()`, `EvidenceStoreHook.on_task_outcome()`. Сам `instrumentation_block.md` живёт вне этого репозитория, вызовы в него добавляются на стороне агента
- [x] Строгая валидация вывода `PromptToGenomeExtractor`: `EXTRACTION_JSON_SCHEMA` + валидатор на stdlib вместо Pydantic (ядро остаётся без зависимостей)
- [x] Framework Evaluation CI: `CI_TIER` required/experimental в каждом шаблоне, падение required валит job, история прогонов сохраняется и при падении
- [x] `framework_version` в наблюдении (`FRAMEWORK_PACKAGE` + `importlib.metadata`)
- [x] Число уникальных геномов в `trust_reality_report()` (`n_unique_genomes`)
- [x] Сверка `MODEL_VERSION` с моделью из ответа провайдера (`observed_model_version`); для фреймворков, чей результат не содержит модель, сверка честно не проводится

### v0.9.0: Evidence Graph (выполнено)

- [x] Доноры доказательств с группами независимости, доказательства с уровнем качества Q0-Q4 (`agenomics/evidence_graph.py`, AEP-001 v1.1)
- [x] Prediction (Trust Score, замороженный до задачи, с `target` и `horizon`) и Outcome (исход от конкретного донора, строго позже заморозки). Заменяет прежние пункты «Outcome Model» и «`PredictionSnapshot`»
- [x] `evidence_profile()`: объём, качество и независимость доказательств раздельно
- [x] `framework_evaluation` на новой схеме: runtime-монитор и сканер секретов как доноры, предсказание до каждого прогона
- [x] `genome_hash` в `framework_evaluation` описывает конфигурацию агента, а не состояние, выведенное из истории: число уникальных геномов перестало быть артефактом
- [x] Тяжесть инцидента по классу ошибки; падения из-за окружения не снижают `predictability` и считаются отдельно как надёжность запуска

### v0.9.1: Validation Engine (выполнено)

- [x] ROC-AUC, PR-AUC, Brier, калибровка (ECE) по парам Prediction → Outcome, с меткой `evidence_strength` (`agenomics/validation.py`, `agenomics validate`)
- [x] Кластерный bootstrap CI по агентам, temporal holdout, baseline: константа, majority class, историческая частота инцидентов агента. Победа над baseline засчитывается только если CI разницы AUC выше нуля
- [x] Уровни наблюдения и агента (Spearman), число конфигураций; фильтры по `outcome_type`, `independence_group`, `verification`, `target`; предсказания с `infrastructure_error` исключаются целиком
- [x] Отчёт в каждом прогоне Framework Evaluation (информационный, CI не валит)

### v0.9.2: Outcome hardening (выполнено)

- [x] Отдельные цели предсказаний (`runtime_failure`, `security_incident`, `task_failure`) вместо общего `incident_in_run`; Validation Engine проверяет каждую отдельно и отказывается смешивать цели
- [x] Донор `task_checker` (Q3): детерминированная проверка ответа агента в 4 шаблонах с однозначным ответом
- [x] В отчёте Validation Engine доноры, группы независимости, подтверждённые пары; исходы раньше заморозки отбрасываются повторно
- [x] CI: ключ кэша с `run_attempt` (ручной Re-run терял историю), `ubuntu-24.04`, actions на Node 24

### v0.9.x: дальше

- [x] Задачи с проверяемым ответом для всех 19 шаблонов (v0.9.4): `task_failure` измеряется у каждого агента
- [x] v0.9.5 Validation Integrity: `task_outcome` пуст при сбое окружения; `PROMPT_VERSION` у всех шаблонов; шапка отчёта с объёмом и качеством данных (Q0–Q4); `incident_in_run` помечена как устаревшая цель; эталон данных v0.9.3; ошибки провайдера в Griptape/Agno/Swarms больше не выглядят как неверный ответ
- [ ] После v0.9.5 новых функций не добавлять: копить проспективные предсказания (100+, затем 500+) на разных задачах, промптах и моделях, затем решение о 1.0

- [ ] Фильтр по `quality_level`: у исходов его нет, он есть у доказательств; нужно решить, как связывать
- [ ] Статистика на уровне конфигурации (`genome_hash`) как отдельный уровень, а не только счётчик
- [ ] LLM-судьи как доноры (`judge`): поведенческая классификация ошибок (hallucination/wrong_decision/reasoning_error) и токсичность в Adversarial Suite. Требует ключа API и решения о модели судьи
- [ ] Adversarial-пробы в `framework_evaluation`: шаблонам нужна функция `ask(prompt)` помимо `run()`

### Release Candidate (после накопления данных)

- [ ] `/api/v1` с аутентификацией, rate limiting, structured errors
- [ ] Расширение CLI: `audit`, `drift`, `evidence export` сверх 5 команд из v0.7.10
- [ ] PostgreSQL как опциональный бэкенд `EvidenceStore`
- [ ] `pip-audit`/`bandit`/security scanning в CI
- [ ] Unified `AgentEvaluation`: genome/phenotype/trust/compatibility/drift/evidence в одной модели

### v1.0: Stable

- [ ] `Development Status` classifier → Production/Stable
- [x] Release pipeline: тег → тесты → сборка → smoke test → PyPI (Trusted Publishing) → сверка с манифестом → GitHub Release ([порядок выпуска](IP/RELEASE_POLICY.md))
- [ ] Веб-калькулятор на prizolov.ru (перенесён из v0.8)
- [ ] Реструктуризация `docs/` на поддиректории, если объём документации разрастётся

### Снято с прежнего плана v0.8 (перенесено за v1.0, не забыто)

Эти пункты стояли в roadmap v0.8 до v0.7.11 и сознательно выведены из него:

- Evolution/Mutation как предложение, требующее подтверждения человеком: не имеет смысла до Genome Versioning (v0.8) и Outcome Model (v0.9), на которые опирается
- Формальный Evaluation Protocol (EP-001..EP-00N с input, ground truth, metric, threshold, CI): частично покрывается Adversarial Evaluation Suite (v0.8) и Temporal Holdout/baseline (v0.9). Как отдельный реестр протоколов не запланирован
- Genome Ledger как публичный сервис: инфраструктура с публичным доступом, та же категория, что и распределённый evidence-кластер ниже
- Мультиязычность за пределами ru/en: не блокирует ни один шаг к v1.0

### Осознанно не в roadmap (v1.1+ как минимум)

Marketplace/плагины, автоматическое «размножение» агентов, распределённый evidence-кластер, SaaS-биллинг, enterprise SSO. Это расползание scope: не трогаем, пока не закрыт барьер с реальными данными.

Полная история изменений: [`CHANGELOG.md`](CHANGELOG.md).

## Авторство и происхождение

**Agenomics** · автор Dm.Andreyanov · бренд Prizolov Lab · © 2026 · лицензия Apache-2.0.

- [`NOTICE`](NOTICE): уведомление об авторстве, которое по лицензии обязано сохраняться при распространении
- [`IP/`](IP/): авторское право, автор, название и бренд, сторонние лицензии, история создания, порядок выпуска версии, реестр компонентов
- [`release/`](release/): манифест каждой версии с SHA-256 файлов по коммиту Git (`scripts/release_manifest.py`)

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
