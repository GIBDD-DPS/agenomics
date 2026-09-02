# 🧬 Agenomics

**Genetics for AI Agents — predictability and compatibility scoring for autonomous agent personalities.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-v0.3.0-orange.svg)](CHANGELOG.md)
[![PyPI](https://img.shields.io/badge/PyPI-agenomics-blue.svg)](https://pypi.org/project/agenomics/)

> **Автор**: Dm.Andreyanov
> **Версия**: 0.3.0
> **Связанные проекты**: [Prizolov Lab](https://prizolov.ru) / [Agent Genome Mapping (AGM)](https://github.com/GIBDD-DPS/agent-genome-mapping)
>
> ⚠️ Методология следует **semver 0.x** — до релиза `1.0.0` обратная
> совместимость API не гарантируется между minor-версиями. Между 0.2 и 0.3
> уже менялась сигнатура `TrustScorer()` (добавлены параметры).

---

## Что это

**Agenomics** — методология и open-source инструментарий для оценки **предсказуемости личности** ИИ-агента и его **совместимости** с другими агентами в команде, построенные на биологической метафоре генома.

В отличие от существующих подходов к «доверию к ИИ-агентам» (криптографическая идентичность, лимиты трат, блокчейн-подписи — см. Agent Passport Standard, AgenticTrust и др.), Agenomics фокусируется на другом вопросе:

> Не «можно ли доверить агенту деньги», а **«предсказуемо ли ведёт себя личность агента, и уживётся ли она с другими агентами в команде»**.

## Ключевая идея

Каждый агент описывается **геномом** — структурированным набором параметров:

- `cognitive_genes` — как агент мыслит (глубина рассуждений, креативность, риск-толерантность)
- `ethics_genes` — какие ограничения соблюдает (bias threshold, hard constraints)
- `social_genes` — как взаимодействует (стиль общения, разрешение конфликтов)
- `meta_genes` — как эволюционирует (скорость мутации, критерий отбора)

На основе генома вычисляется:

1. **Trust Score** (0–100) — итоговая оценка предсказуемости и безопасности агента с учётом критичности домена (Impact Tier) и уровня автономности
2. **Compatibility Score** — насколько хорошо два и более агентов сработаются в одной команде

Полная формула, таблица маппинга «поле генома → ось» и объяснение шкал — в [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

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
print(result.confidence)        # High / Medium / Low — НЕ то же самое, что score
print(result.breakdown)         # разбивка по 5 осям
print(result.capped_reason)     # если применён потолок автономности
print(result.attribution)       # ссылка на методологию/автора
```

Значения `bias_control`, `transparency`, `data_safety` и т.д. должны быть
в диапазоне `[0, 100]`, `drift_rate` — в `[0.0, 1.0]`. Значения вне
диапазона вызывают `ValueError` уже на этапе создания `AgentGenome`.

### Настраиваемые профили весов (v0.3)

```python
from agenomics import TrustScorer, TRUST_WEIGHT_PROFILES

print(list(TRUST_WEIGHT_PROFILES.keys()))
# ['default', 'healthcare', 'finance', 'content']

scorer = TrustScorer(weight_profile="healthcare")  # DataSafety весит больше
# или произвольные веса (должны суммироваться в 1.0):
scorer = TrustScorer(weights={"transparency": 0.4, "bias_control": 0.3, "data_safety": 0.1, "predictability": 0.1, "accountability": 0.1})
```

### Compatibility Scorer — совместимость команды агентов

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

### Роли агентов (v0.3) — различие не всегда плохо

```python
reviewer = AgentGenome(id="reviewer", role="reviewer", bias_control=85, risk_tolerance=10, social_style=50)
executor = AgentGenome(id="executor", role="executor", bias_control=85, risk_tolerance=90, social_style=50)

result = CompatibilityScorer().score_pair(reviewer, executor)
print(result.complementary_roles)         # True
print(result.breakdown["risk_tolerance"]) # 100.0 — разница риск-толерантности не штрафуется,
                                           # т.к. это осознанный дизайн (осторожный ревьюер
                                           # при рискованном исполнителе), а не конфликт
```

### Множественный domain — гибкий Tier

```python
# Агент поддержки, который иногда обрабатывает возвраты денег —
# Tier берётся как максимум (самый строгий) среди всех доменов.
genome = AgentGenome(id="support-refunds", domains=["support", "finance"])
print(genome.tier)  # ImpactTier.TIER_3
```

### Веб-API

Методология доступна и как HTTP-API — `POST /score` и `POST /compatibility`.
Конфиг для самостоятельного деплоя (например, на Amvera) — `amvera.yml`.
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

## Структура репозитория

```
agenomics/
├── agenomics/              # ядро: AgentGenome, TrustScorer, CompatibilityScorer, api.py
├── prompts/                 # системные промпты (Trust Auditor и др.)
├── docs/                     # методология, whitepaper
├── tests/                     # тесты (27+, включая валидацию и v0.3-улучшения)
├── .github/workflows/          # CI — тесты запускаются на каждый push/PR
├── amvera.yml                   # конфиг деплоя веб-API на Amvera
├── requirements.txt               # зависимости для ЗАПУСКА (тесты, FastAPI/uvicorn)
├── pyproject.toml                  # метаданные пакета для PyPI (ядро — без внешних зависимостей)
├── CHANGELOG.md                     # история версий
└── CONTRIBUTING.md                   # как предложить изменения
```

### Почему `requirements.txt` и `pyproject.toml` — не дублирование

Это может выглядеть избыточным, поэтому явно: **`pyproject.toml`** описывает
только сам пакет `agenomics`, который ставится через `pip install agenomics` —
у ядра библиотеки нет внешних зависимостей, кроме стандартной библиотеки
Python. **`requirements.txt`** нужен для *запуска этого репозитория* —
тестов (`pytest`) и веб-API (`fastapi`, `uvicorn`), в том числе через
`amvera.yml` → `build.requirementsPath`. Если вы просто ставите пакет
через pip — `requirements.txt` вам не нужен.

## Методология

Полное описание методологии, формула, таблица маппинга «поле генома →
ось», объяснение шкал (`social_style`, `risk_tolerance`) и диапазоны
валидации — в [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Roadmap

- [x] v0.1 — формула Trust Score, Tier-множитель, потолок автономности
- [x] v0.1 — промпт Trust Auditor (см. `prompts/`)
- [x] v0.2 — Compatibility Scorer между несколькими агентами
- [x] v0.2 — веб-API (`/score`, `/compatibility`) на Amvera
- [x] v0.2 — публикация пакета на PyPI
- [x] v0.3 — настраиваемые профили весов (`healthcare`/`finance`/`content`/`safety_critical`)
- [x] v0.3 — роли агентов в Compatibility Score (`executor`/`reviewer`)
- [x] v0.3 — множественный `domain`, гибкая классификация Tier
- [x] v0.3 — Confidence (уверенность в оценке, отдельно от score)
- [x] v0.3 — атрибуция с бэклинком в промпте, коде и API
- [x] v0.3 — валидация диапазонов входных данных
- [x] v0.3 — CI (GitHub Actions), CHANGELOG.md, CONTRIBUTING.md
- [ ] v0.4 — веб-калькулятор на prizolov.ru
- [ ] v0.4 — публичный реестр верификации (Genome Ledger)
- [ ] v0.4 — обратная связь с реальными инцидентами (не только декларативная оценка)

Полная история изменений — в [`CHANGELOG.md`](CHANGELOG.md).

## Тесты и CI

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -v
```

Тесты автоматически запускаются на каждый push/PR через GitHub Actions
(см. `.github/workflows/`).

## Contributing

См. [`CONTRIBUTING.md`](CONTRIBUTING.md). Обратная связь и предложения —
через GitHub Issues.

## Лицензия

Apache 2.0 — см. [LICENSE](LICENSE).

---

© 2026 Dm.Andreyanov. Agenomics — независимый проект, развивающий идеи Agent Genome Mapping™ (Prizolov Lab).
