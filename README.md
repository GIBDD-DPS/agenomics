# 🧬 Agenomics

**Genetics for AI Agents — predictability and compatibility scoring for autonomous agent personalities.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-v0.1--draft-orange.svg)](#)

> **Автор**: Dm.Andreyanov
> **Версия**: 0.1.0 (draft)
> **Связанные проекты**: [Prizolov Lab](https://prizolov.ru) / [Agent Genome Mapping (AGM)](https://github.com/GIBDD-DPS/agent-genome-mapping)

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

## Быстрый старт

```bash
pip install -e .
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

scorer = TrustScorer()
result = scorer.score(genome)

print(result.score)          # 0-100
print(result.label)          # Trusted / Conditional / High Risk
print(result.breakdown)      # разбивка по 5 осям
print(result.capped_reason)  # если применён потолок автономности
```

## Структура репозитория

```
agenomics/
├── agenomics/           # ядро: AgentGenome, TrustScorer
├── prompts/             # системные промпты (Trust Auditor и др.)
├── docs/                # методология, whitepaper
├── tests/               # тесты
├── amvera.yml           # конфиг деплоя на Amvera
└── requirements.txt
```

## Методология

Полное описание методологии — в [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Roadmap

- [x] v0.1 — формула Trust Score, Tier-множитель, потолок автономности
- [ ] v0.1 — промпт Trust Auditor (готов, см. `prompts/`)
- [ ] v0.2 — Compatibility Scorer между несколькими агентами
- [ ] v0.2 — веб-калькулятор (по аналогии с инструментами Prizolov Lab)
- [ ] v0.3 — публичный реестр верификации (Genome Ledger)

## Лицензия

Apache 2.0 — см. [LICENSE](LICENSE).

---

© 2026 Dm.Andreyanov. Agenomics — независимый проект, развивающий идеи Agent Genome Mapping™ (Prizolov Lab).
