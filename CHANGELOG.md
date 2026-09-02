# Changelog

Все значимые изменения проекта Agenomics фиксируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/),
версионирование — [Semantic Versioning](https://semver.org/) (0.x — API нестабилен).

## [0.4.0] — 2026-09-03

### Добавлено
- **Drift Monitor** (`agenomics/drift.py`) — отслеживает историю Trust Score агента во времени, определяет тренд (improving/stable/degrading) и подаёт алерт при деградации
- **Incident Feedback Loop** (`agenomics/feedback.py`) — пересчитывает декларативный Trust Score в "наблюдаемый" (Observed Score) с учётом реальных подтверждённых инцидентов (minor/moderate/severe)
- **Genome Ledger** (`agenomics/ledger.py`) — append-only реестр записей аудита с хэш-цепочкой для базовой целостности (локальный прототип, не блокчейн)
- **Genome Matchmaker** (`agenomics/matchmaker.py`) — подбирает оптимальное назначение ролей для команды агентов по максимальному Compatibility Score (полный перебор, до 8 кандидатов)
- **Chain Risk Aggregator** (`agenomics/chain.py`) — считает надёжность последовательного пайплайна агентов как произведение вероятностей, а не среднее (в отличие от Compatibility Score для параллельной команды)
- **Prompt-to-Genome Extractor** (`agenomics/extractor.py`) — автоматическое извлечение `AgentGenome` из системного промпта агента через pluggable LLM-клиент (библиотека не делает сетевых вызовов сама)
- **Reports** (`agenomics/reports.py`) — `trust_report()` и `compatibility_report()`, готовые Markdown-отчёты вместо сырых dataclass
- 20 новых тестов (`tests/test_v04_modules.py`), итого 47/47 тестов проходят

## [0.3.0] — 2026-09-02

### Добавлено
- Настраиваемые профили весов Trust Score (`default`, `healthcare`, `finance`, `content`) и Compatibility Score (`default`, `safety_critical`)
- Роли агентов (`role` поле): расхождение `risk_tolerance` между `executor` и `reviewer` не штрафуется в Compatibility Score
- Множественный `domain` (поле `domains`) — Tier берётся по самому строгому домену
- `Confidence` (High/Medium/Low) — уверенность в оценке, отдельно от самого `score`
- Атрибуция (`attribution` поле) — во всех результатах, в промпте (обязательная последняя строка) и в API
- Валидация диапазонов входных данных в `AgentGenome` (`__post_init__`, `ValueError` при выходе за `[0, 100]` / `[0.0, 1.0]`)
- CI (GitHub Actions) — тесты запускаются на каждый push/PR
- `CHANGELOG.md`, `CONTRIBUTING.md`

### Изменено
- `TrustScorer()` и `CompatibilityScorer()` теперь принимают `weight_profile` или `weights` в конструкторе (изменение сигнатуры — см. предупреждение о semver 0.x)
- `api.py`: эндпоинты `/score` и `/compatibility` теперь принимают `weight_profile`, `role`, `domains`; ответы включают `confidence`, `confidence_ratio`, `attribution`
- `amvera.yml`: исправлен ключ `run.command` (ранее использовался несуществующий `run.args`)
- `docs/METHODOLOGY.md`: добавлена таблица маппинга «поле генома → ось формулы», объяснение шкалы `social_style`, диапазоны валидации

### Исправлено
- README.md синхронизирован с реальным состоянием репозитория (ранее отставал на несколько версий от PyPI)

## [0.2.0] — 2026-09-01

### Добавлено
- `CompatibilityScorer` — оценка совместимости пары/команды агентов по 4 осям (ethics, risk_tolerance, social_style, accountability)
- Веб-API (`agenomics/api.py`, FastAPI): эндпоинты `POST /score`, `POST /compatibility`, `GET /health`
- Деплой на Amvera (`amvera.yml`)
- Публикация пакета на PyPI (`pip install agenomics`)

## [0.1.0] — 2026-08-31

### Добавлено
- Первая версия `TrustScorer` и `AgentGenome`
- Формула Trust Score по 5 осям (Transparency, BiasControl, DataSafety, Predictability, Accountability)
- Tier-множитель для критичных доменов (TIER_3, ×1.3)
- Жёсткий потолок Trust Score (≤70) для Autonomous-агентов без журнала аудита
- Промпт Trust Auditor
- Открытый репозиторий на GitHub (Apache 2.0)
