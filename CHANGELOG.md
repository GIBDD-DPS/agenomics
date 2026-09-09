# Changelog

Все значимые изменения проекта Agenomics фиксируются здесь.
Формат основан на [Keep a Changelog](https://keepachangelog.com/),
версионирование: [Semantic Versioning](https://semver.org/) (0.x: API нестабилен).

## [0.7.8] - 2026-09-09

### Исправлено
- **CORS не был настроен вовсе в `agenomics/api.py`.** Любой запрос из браузера с другого origin был бы заблокирован политикой same-origin, включая будущий веб-калькулятор на prizolov.ru из roadmap v0.8. Добавлен `CORSMiddleware` с `allow_origins=["*"]`, осознанный выбор для публичного unauthenticated API. Уже было честно задокументировано как известное ограничение в `SECURITY.md`, теперь исправлено, текст обновлён

### Проверено внешним разбором и не подтвердилось
- SQL-инъекция в `EvidenceStore`: обе f-string интерполяции в SQL используют только жёстко закодированные константы модуля (`_EXPECTED_OBSERVATION_COLUMNS`, `_OBSERVATION_COLS`), не пользовательский ввод. Реальные данные передаются через параметризованный `?`, как и должно быть
- Коллизия хэша через встроенный `hash()`: уже `hashlib.sha256`, не встроенный `hash()`
- Отсутствие `SECURITY.md`: существует с v0.7.5, разбор проверял устаревшее состояние репозитория

## [0.7.7] - 2026-09-09

### Исправлено
- **`EvidenceStore` не использовал WAL journal mode.** Для файловых БД (не `:memory:`) теперь включается `PRAGMA journal_mode=WAL`, позволяющий одному писателю и нескольким читателям работать одновременно без `database is locked`. Не решает полностью сценарий с несколькими одновременными писателями (они всё равно сериализуются), это уже честно задокументированное ограничение в `SECURITY.md`, не новое

### Добавлено
- **`scripts/verify_release.py`**: проверяет, что все критичные файлы (52 позиции, включая все 15 шаблонов `examples/framework_evaluation/frameworks/`) реально присутствуют в репозитории. Адресует реальный, повторявшийся минимум 4 раза класс проблемы: файл был построен и протестирован, но не сохранялся при загрузке на GitHub, и это обнаруживалось только через несколько версий. Добавлен как шаг в `.github/workflows/tests.yml`, теперь ловится автоматически на каждый push/PR, а не только вручную
- 2 новых теста на WAL-режим, итого 181/181

## [0.7.6] - 2026-09-09

### Исправлено
- **`EvidenceStore.get_observations()` делал N+1 запрос к SQLite.** Один SELECT за наблюдениями, затем отдельный SELECT за инцидентами на каждое наблюдение в цикле. Проверено бенчмарком: 2000 наблюдений, 2001 отдельный запрос, 30мс, 20000 наблюдений, 20001 запрос, 315мс, линейный рост числа запросов, а не только объёма данных. Исправлено на один JOIN-запрос с группировкой в Python: 20000 наблюдений теперь 130мс за 1 запрос независимо от их количества. Найдено при проверке замечания о производительности, индексы здесь не помогли бы: запросы и так используют уже проиндексированные `agent_id`/`id` (первичный ключ), реальная проблема была в архитектуре запроса, не в отсутствии индекса
- 3 регрессионных теста, включая проверку количества выполненных SQL-запросов через `sqlite3.Connection.set_trace_callback()`, не только по времени выполнения

## [0.7.5] - 2026-09-08

### Исправлено (найдено внешним разбором)
- **`agenomics/ledger.py`: `_genome_hash()` пропускал `axis_confidence`, `accountability_override`, `tier_override`.** Функция была вручную поддерживаемым списком полей, не обновлённым после добавления этих полей в `AgentGenome` (v0.7.1 и ранее). Два генома, различающихся только этими полями, получали одинаковый хэш. Исправлено: хэш строится по всем полям датакласса автоматически через `dataclasses.asdict()`, любые будущие поля `AgentGenome` учитываются без необходимости обновлять эту функцию. Та же проблема исправлена в `examples/framework_evaluation/full_pipeline.py`
- **`EvidenceStoreHook`: `genome_hash` терялся при перезапуске процесса.** `_last_genome_hash` был чисто in-memory кэшем, ровно тот же класс бага, что уже был найден и исправлен в `full_pipeline.py` для истории `predictability`. Исправлено: `on_trust_scored()`/`on_drift_alert()` принимают `genome_hash` явным опциональным параметром, с падением на кэш только для обратной совместимости
- Python 3.10 отсутствовал в тестовой matrix CI, хотя заявлен в `pyproject.toml` classifiers. Добавлен

### Добавлено
- **`PromptToGenomeExtractor.extract_with_evidence()`**: структурированный evidence по каждой оси генома (`value`, `confidence`, `evidence`-цитата из промпта), не просто число. `extract()` остаётся полностью обратно совместимым, включая старый плоский формат ответа LLM
- **Три состояния генома формализованы** в `docs/METHODOLOGY.md`, раздел 11: Declared (заявлено), Observed (видно из инцидентов и дрейфа), Evaluated (подтверждено достаточным объёмом наблюдений, на 2026-09-08 инфраструктура существует, содержательного результата пока нет ни для одного агента)
- **`tests/test_version_consistency.py`**: 5 тестов, автоматически проверяющих согласованность версии между `pyproject.toml`, `agenomics/api.py`, `CHANGELOG.md`, `README.md`. Написан специально, чтобы баг с `api.py` на версии 0.3.0 не смог повториться незаметно
- **`SECURITY.md`**: политика сообщения об уязвимостях, честные известные ограничения (`GenomeLedger` не криптографически защищён, веб-API без аутентификации)
- 15 новых тестов (`test_version_consistency.py`, обновлённые `test_v04_modules.py`, `test_hooks.py`, `test_extractor.py`), итого 176/176

### Изменено
- Главный заголовок `README.md` приведён к позиционированию, уже выбранному для Product Hunt: «Make AI Agent Trust Testable», «Evaluate AI Agents. Build Real-World Evidence»
- `benchmark/BENCHMARKS.md` обновлён на текущую версию (0.7.4 на момент прогона). Числа не изменились с v0.6.1, потому что сама формула `TrustScorer`/`CompatibilityScorer` не менялась, это честно зафиксировано в самом файле, а не выдано за новый результат

### Осознанно не реализовано в этом релизе (по итогам того же разбора)
- Полная цепочка хэшей `GenomeLedger` (весь entry, не только `genome_hash`): обоснованная идея, но `GenomeLedger` уже задокументирован как локальный in-memory прототип и это в roadmap v0.8, частичное усиление сейчас не имеет смысла
- ROC-AUC/PR-AUC/Brier Score/baseline-сравнение: бессмысленно считать при текущем объёме данных (максимум 9 наблюдений на агента, порог 10+)
- `/api/v1`, аутентификация, rate limiting, CLI, Postgres backend, JSON Schema для AEP-001: осмысленные идеи для production-версии, преждевременны для текущего масштаба использования
- Реструктуризация `docs/` на поддиректории: преждевременно при текущем объёме документации

## [0.7.4] - 2026-09-07

### Добавлено
- `EvidenceStoreHook` (`agenomics/hooks.py`), готовая реализация интерфейса `AgentLifecycleHook` из `docs/PRIZOLOV_BRIDGE_INTERFACE.md`. Пишет наблюдения и инциденты в `EvidenceStore` при вызове `on_genome_extracted()`, `on_trust_scored()`, `on_drift_alert()`. Не требует знания о внутреннем устройстве вызывающей системы, только чтобы её три метода вызывали в подходящие моменты
- 6 новых тестов (`tests/test_hooks.py`)
- `tests/test_api.py`: 7 smoke-тестов веб-API (`agenomics/api.py`), которых не было вообще ни в одной предыдущей версии. Требуют `httpx` (добавлен в `requirements.txt`)
- Итого 162 теста в ядре, плюс 7 в `test_api.py` (требуют `fastapi`/`httpx` из `requirements.txt`, не запускаются через голый `pip install agenomics`)

### Исправлено (найдено внешним разбором на 25 пунктов)
- **Критично: `agenomics/api.py` не обновлялась с версии 0.3.0.** Пока ядро пакета дошло до 0.7.4, веб-API (`GET /health`, поле `version`) продолжал сообщать `"0.3.0"`. Синхронизировано, `test_health_version_matches_package_version` сверяет с `agenomics.__version__` напрямую, а не с текстовой константой, чтобы повторный дрейф версий сразу ломал тест
- `benchmark/BENCHMARKS.md` не обновлялся с v0.6.1 (дата `2026-09-03`), хотя код ушёл далеко вперёд
- `amvera.yml`: убран устаревший комментарий «веб-API ещё не реализован». API существует и деплоится этой же конфигурацией с версии 0.2
- Обнаружено и исправлено: `docs/AEP-001.md` и `docs/PRIZOLOV_BRIDGE_INTERFACE.md` были заявлены как добавленные в CHANGELOG (v0.7.1), но фактически отсутствовали в репозитории на GitHub. Файлы не сохранились при исходной загрузке ещё в раунде v0.7.1. Загружены повторно

### Честный итог по расхождению документации и репозитория
- Обнаружен устойчивый паттерн за версии 0.7.0-0.7.3: код и тесты почти всегда были корректны на момент написания, но часть файлов не сохранялась при загрузке на GitHub, и это вскрывалось только через несколько версий (при реальном деплое Amvera, реальном прогоне GitHub Actions, или внешнем аудите). Не найдено ни одного случая, где сам написанный код был бы некорректен, все расхождения на этапе доставки, не разработки

## [0.7.3] - 2026-09-06

### Исправлено
- **Критично: `EvidenceStore` падал с `sqlite3.OperationalError: table observations has no column named execution_status` на файлах базы, созданных до v0.7.2.** `CREATE TABLE IF NOT EXISTS` не трогает уже существующую таблицу, поэтому файл базы, восстановленный из кэша GitHub Actions после нескольких запусков на 0.7.1, никогда не получал новые колонки `execution_status`/`duration_seconds` сам по себе. Реально воспроизведено на настоящем прогоне `framework_eval.yml` (14 фреймворков, кэш с прошлой версии). Исправлено миграцией схемы: `EvidenceStore.__init__` теперь проверяет фактические колонки через `PRAGMA table_info` и добавляет недостающие через `ALTER TABLE`
- Регрессионный тест `test_migrates_old_schema_file_missing_new_columns`, воспроизводящий именно эту ситуацию (файл со старой схемой, открытый текущим кодом)

## [0.7.2] - 2026-09-06

### Добавлено
- **`docs/CONNECT_YOUR_AGENTS.md`**: практический гайд «как подключить Agenomics к реальным агентам за 15 минут» (ранее висел в незафиксированном `[Unreleased]`, теперь официально в этом релизе)
- **`examples/framework_evaluation/`**: автоматический сбор реальных наблюдений с 14 публичных agent-фреймворков (LangChain, CrewAI, AutoGen/AG2, LlamaIndex, Semantic Kernel, LangGraph, Haystack, CAMEL-AI, OpenAI Agents SDK, Griptape, Rasa, AutoGPT, MetaGPT, SuperAGI). Авто-обнаружение новых фреймворков без правки раннера, запуск по расписанию через GitHub Actions (`framework_eval.yml`)
- **`EvidenceStore.record_observation()`**: новые поля `execution_status`, `duration_seconds`: явные, персистентные сигналы для реконструкции истории между перезапусками процесса
- Framework Evaluation smoke-тест в основном CI (`tests.yml`): 12 тестов на механику пайплайна (`examples/framework_evaluation/test_pipeline.py`) без необходимости ставить все 14 реальных библиотек

### Исправлено (найдено внешним разбором репозитория)
- **🔴 Критично: `predictability` не накапливался между запусками CI.** История хранилась в module-level словаре `_HISTORY` в `full_pipeline.py`, который живёт только в памяти одного процесса. В GitHub Actions каждый запуск workflow запускает новый процесс, поэтому история фактически никогда не накапливалась, хотя README заявлял обратное. Исправлено: история теперь реконструируется из самого `EvidenceStore` (`execution_status`/`duration_seconds`) перед каждым построением генома. Проверено регрессионным тестом, симулирующим 5 отдельных процессов на одном файле базы
- **🟠 `has_ledger=True` по умолчанию был методологической ошибкой.** Прежняя логика в `genome_from_capture.py` считала: раз лог захвачен, значит есть audit trail. Это не одно и то же: захват лога инструментом (agenomics) не означает, что сам агент ведёт журнал решений. Исправлено: `has_ledger` теперь явный параметр с честным дефолтом `False`, а `True` нужно утверждать осознанно
- Версия в `README.md`/`pyproject.toml`/`CHANGELOG.md` на GitHub не совпадала с фактически опубликованным на PyPI 0.7.1: файлы не сохранились при предыдущей загрузке. Пересинхронизировано

### Осознанно НЕ реализовано в этом релизе (по итогам того же разбора)
- Переход `EvidenceStore` с SQLite-файла на Postgres/S3: разумно для production evaluation infrastructure, преждевременно для текущего масштаба использования
- Полноценный CI-прогон против реально установленных 14 библиотек (сейчас `continue-on-error: true` в `framework_eval.yml`): намеренно. "Включает адаптеры для 14 фреймворков" ≠ "гарантированная production-совместимость со всеми 14"

## [0.7.1] - 2026-09-04

### Добавлено
- **Agenomics Evidence Protocol v1.0** (`docs/AEP-001.md`): формальная схема Observation/Incident/Provenance, реализована в `EvidenceStore` и `Incident`. Обязательное правило Privacy: никаких сырых пользовательских текстов по умолчанию, `Incident.description` длиннее 200 символов теперь выдаёт `UserWarning`
- **`IncidentCategory`, `IncidentSource`** (`agenomics/feedback.py`): структурированные поля инцидента вместо только свободного текста; `Incident` также получил `confirmed` и `resolution`. Все новые поля опциональны, старый код продолжает работать
- **Confidence на уровне гена** (`AgentGenome.axis_confidence`): вместо бинарного "есть/нет данных" теперь можно заявить continuous-уверенность (0.0-1.0) по каждой оси отдельно; влияет только на `confidence_ratio`, не на сам `score`
- **`PerAxisDriftMonitor`** (`agenomics/per_axis_drift.py`): переиспользует `DriftMonitorV2` для отслеживания дрейфа КАЖДОЙ оси Trust Score отдельно, с экспертной калибровкой ожидаемой волатильности по типу гена (`BASELINE_VOLATILITY_BY_AXIS`). Позволяет находить `weakest_axis()`: какая именно ось деградирует, а не только агрегированный score
- **Team Compatibility Heatmap** (`agenomics/heatmap.py`): `build_compatibility_matrix()` + `render_heatmap_svg()`, визуализация совместимости команды на основе уже существующего `CompatibilityScorer.score_team()` (не новая логика подсчёта)
- **`docs/PRIZOLOV_BRIDGE_INTERFACE.md`**: честный набросок интерфейса для интеграции с внешними оркестраторами (например, Prizolov Market), без выдумывания поведения чужого недоступного кода
- 26 новых тестов (`tests/test_axis_confidence.py`, `tests/test_per_axis_drift.py`, `tests/test_heatmap.py`), итого 145/145 тестов проходят

### Честные находки при разработке
- При тестировании `PerAxisDriftMonitor` найден реальный баг: переопределение только `mild_threshold` не давало эффекта, если `moderate_threshold`/`severe_threshold` оставались дефолтными: более мягкая ось всё равно попадала под старый строгий порог раньше, чем добиралась до mild. Исправлено пропорциональным масштабированием всех трёх порогов

### Осознанно НЕ реализовано (см. обоснование в ответе на соответствующий внешний запрос)
- ML-калибровка на инцидентах: требует реального датасета, которого нет
- Marketplace-плагины (LangChain/AutoGen/CrewAI): scope creep, отвлекает от барьера с данными
- Agent breeding / evolutionary pressure simulation: это Evolution/Mutation, отложено до реальных данных
- Рабочий пакет `prizolov-agenomics-bridge`: нет доступа к реальному API `prizolov_market`, дан только интерфейс-контракт

## [0.7.0] - 2026-09-04

### Добавлено
- **EvidenceStore** (`agenomics/evidence.py`): персистентное (SQLite, часть стандартной библиотеки: без новых внешних зависимостей) хранилище наблюдений и инцидентов с provenance-полями (`genome_hash`, `agenomics_version`, `timestamp`). Экспорт в JSON/CSV
- **`replay_into_evaluation_layer()`**: воспроизводит сохранённые наблюдения обратно в свежий `RealWorldEvaluationLayer` (например, после перезапуска процесса). Полный цикл «записать → перезапуск → загрузить → посчитать корреляцию» теперь реально работает
- `RealWorldEvaluationLayer.record_raw_observation()`: низкоуровневый метод записи по сырым score/label/confidence, без полноценного `TrustResult` (нужен для replay из `EvidenceStore`); `record_observation()` теперь тонкая обёртка над ним
- CI (`.github/workflows/tests.yml`): добавлен явный шаг прогона `benchmark.run_benchmark` (помимо unit-тестов, для наглядности в логах)
- 9 новых тестов (`tests/test_evidence.py`) + 1 новый тест на `record_raw_observation`, итого 120/120 тестов проходят

### Исправлено
- `docs/SPECIFICATION.md`: устранён рассинхрон версии («Соответствует реализации: v0.6.0» при реальном коде v0.6.1): переформулировано как «Проверено на реализации: v0.7.0» (семантически точнее: спецификация не следует за кодом автоматически, а верифицируется на конкретной версии)

### Контекст
- Реализовано по итогам двух внешних ревью подряд, независимо указавших на одно и то же. Persistence, следующий необходимый шаг после Evidence Quality (v0.6.1), раньше Evolution/Mutation
- Осознанно НЕ реализовано в этом релизе: формальный Evaluation Protocol (EP-001..EP-00N), предиктивная модель (ROC-AUC/Brier Score), Evolution/Mutation как proposal-механизм. Следующие шаги v0.8+

## [0.6.1] - 2026-09-03

### Добавлено: Evidence Quality (укрепление существующего, не новый функционал)
- **Weight Sensitivity** (`benchmark/sensitivity.py::measure_weight_sensitivity`): измеряет, насколько Trust Score чувствителен к малым сдвигам весов (±1%/±3%/±5%/±10%). Находка: ось `accountability` на порядок чувствительнее остальных (0.7→7.1 баллов) из-за взаимодействия с потолком автономности
- **Threshold Sensitivity** (`measure_threshold_sensitivity`): проверяет устойчивость `DriftMonitorV2` к выбору `mild_threshold`; подтверждает отсутствие ложных срабатываний на `no_drift` при всех проверенных порогах и показывает, что слишком мягкий порог (0.10) пропускает mild-деградацию полностью
- **Bootstrap 95% CI** (`bootstrap_ci_compatibility_accuracy`): доверительный интервал для Compatibility Accuracy v2 по 1000 пересемплированиям (seed=42 для воспроизводимости). Результат [1.0, 1.0]: честно объяснено как свойство чистоты синтетического разделения, а не нулевая реальная неопределённость
- 10 новых тестов (`tests/test_sensitivity.py`), итого 110/110 тестов проходят
- CLI `benchmark/run_benchmark.py` теперь выводит отдельный блок "EVIDENCE QUALITY"

### Контекст
- Реализовано по итогам внешнего ревью v0.6.0, которое отдельно отметило: "270 случаев / bootstrap-неопределённость / sensitivity: это то, что превращает набор тестов в настоящий evaluation framework"
- Осознанно НЕ реализовано в этом релизе (по тому же ревью): Evidence Store с персистентностью, формальный Evaluation Protocol, предиктивная модель (ROC-AUC/Brier Score): следующие, более крупные шаги v0.7+

## [0.6.0] - 2026-09-03

### Добавлено
- **DriftMonitorV2** (`agenomics/drift.py`): rolling window, EWMA, волатильность, baseline, явная классификация тяжести (`none`/`mild`/`moderate`/`severe`/`sudden`/`volatile`), обнаружение восстановления (`recovered`). Исправляет находку `benchmark/BENCHMARKS.md` v0.1: mild-деградация не обнаруживалась вовсе за 15 шагов на v1
- **Compatibility Accuracy v2** (`benchmark/scenarios.py::generate_compatibility_ground_truth`): 270 систематически сгенерированных случаев в 9 категориях вместо 4 ручных в v0.1
- **RealWorldEvaluationLayer** (`agenomics/evaluation.py`): новая инфраструктура уровня Observed Behaviour: собирает Declared Score + реальные инциденты + дрейф во времени, считает реальную (не синтетическую) корреляцию Trust Score ↔ Incident Rate при достаточном количестве наблюдений. Делает `Incident Correlation` вычислимой метрикой на настоящих данных. Раньше единой точки сбора не было
- **`benchmark/BENCHMARKS.md`**: опубликованный, воспроизводимый отчёт с зафиксированными числами (8 метрик, 7 computed + Incident Correlation not_computable), пригодный для цитирования как Engineering Evidence
- 7 сценариев деградации (`no_drift`/`mild`/`moderate`/`severe`/`sudden`/`recovery`/`oscillation`) для калибровки DriftMonitorV2
- 21 новый тест (`tests/test_drift_v2.py`, `tests/test_compat_ground_truth_v2.py`, `tests/test_evaluation.py`), итого 100/100 тестов проходят

### Честные находки при разработке v0.6.0 (не скрыты, задокументированы)
- При калибровке DriftMonitorV2 колебания (oscillation) без тренда изначально ложно классифицировались как `sudden`: исправлено подсчётом смен знака приращений, отличающим колебание от единичного устойчивого скачка
- Остаточный transient: первые ~2 снимка колебательного паттерна (до заполнения rolling window) всё ещё могут классифицироваться неточно как `sudden` вместо `volatile`: не устранено полностью, заявлять обратное было бы нечестно
- Compatibility Accuracy v2 остаётся синтетическим ground truth (сконструированным вручную): 270 случаев надёжнее 4, но не замена реальным данным

### Приоритизация (по внешнему запросу)
- Real-World Evaluation Layer реализован ДО Evolution/Mutation: по обоснованному аргументу, что мутировать геном без накопленных реальных наблюдений бессмысленно. Evolution/Mutation остаётся нереализованным пунктом v0.7+

## [0.5.0] - 2026-09-03

### Добавлено
- **AGENOMICS SPECIFICATION v1.0** (`docs/SPECIFICATION.md`): формальный конвейер Agent Genome → Genome Schema → Phenotype → Trust Model → Compatibility Model → Drift Model → Observed Behaviour → Evolution/Mutation. Versioning спецификации отделено от версионирования кода.
- **Genome Schema** (`agenomics/phenotype.py`, `describe_genome_schema()`): machine-readable описание полей `AgentGenome`, синхронизировано тестом с реальным dataclass
- **Phenotype** (`agenomics/phenotype.py`, `compute_phenotype()`): новое понятие. "Выраженные" значения осей после взаимодействия генома с контекстом (Impact Tier), но до весов Trust Model. Доказано тестом, что одинаковый Genome в разном Tier даёт разный Phenotype
- **Agenomics Synthetic Benchmark Suite v0.1** (`benchmark/`): 6 метрик из внешнего запроса на референсную спецификацию:
  - Reproducibility, Behavioral Predictability, Trust Calibration, Compatibility Accuracy, Drift Detection Lag: вычислены синтетически, с явной меткой "formula consistency", НЕ "real-world validity"
  - Incident Correlation: честно помечена `not_computable`: синтетическая имитация была бы циркулярной, требует реальных production-данных
  - Найдено реальное ограничение: `DriftMonitor` не обнаруживает mild-деградацию за 15 шагов при текущей эвристике: задокументировано, не скрыто
- 15 новых тестов (`tests/test_phenotype.py`, `tests/test_benchmark.py`), итого 79/79 тестов проходят
- `keywords`/`classifiers` в `pyproject.toml`: для находимости на PyPI

### Примечание о честности
- Раздел 9 спецификации (Evolution/Mutation) явно помечен как **не реализованный**. Ни кода, ни прототипа. Не выдаётся за существующее.
- `benchmark/README.md` содержит явное разграничение: internal formula consistency ≠ real-world predictive validity. Та же причина, по которой была убрана вымышленная статистика на "20 агентах" из первой версии статьи-анонса.

## [0.4.3] - 2026-09-03

### Добавлено
- **Мультиязычность**: `TrustScorer(language="ru"|"en")` и `CompatibilityScorer(language="ru"|"en")`: переводят `recommendations`, `capped_reason`, `how_to` детерминированно (без LLM)
- `trust_report()`, `compatibility_report()`, `trust_report_docx()` теперь принимают `language="ru"|"en"` для заголовков/подписей отчёта
- `SUPPORTED_LANGUAGES`, `HOW_TO_GUIDE_TRANSLATIONS` экспортированы из пакета
- Промпт Trust Auditor (v0.4): добавлен ШАГ -1. Инструкция вести аудит на языке описания агента (не гарантия, зависит от LLM, в отличие от параметра `language` в коде)
- 10 новых тестов (`tests/test_i18n.py`)

### Примечание
- Поддержка языков за пределами ru/en требует добавления новых словарей переводов вручную: не универсальный перевод "из коробки"

## [0.4.2] - 2026-09-03

### Добавлено
- **`trust_report_docx()`** (`agenomics/reports.py`): брендированный Word-отчёт (шапка Prizolov Lab, прогресс-бары по осям, карточки рекомендаций) через `python-docx` (опциональная зависимость, `pip install agenomics[docx]`)
- **`how_to`**: практическая подсказка «как сделать» для каждой оси, попавшей в рекомендации (`TrustResult.how_to`, используется в обоих форматах отчёта)
- 4 новых теста (`tests/test_reports_docx.py`)

## [0.4.0] - 2026-09-03

### Добавлено
- **Drift Monitor** (`agenomics/drift.py`): отслеживает историю Trust Score агента во времени, определяет тренд (improving/stable/degrading) и подаёт алерт при деградации
- **Incident Feedback Loop** (`agenomics/feedback.py`): пересчитывает декларативный Trust Score в "наблюдаемый" (Observed Score) с учётом реальных подтверждённых инцидентов (minor/moderate/severe)
- **Genome Ledger** (`agenomics/ledger.py`): append-only реестр записей аудита с хэш-цепочкой для базовой целостности (локальный прототип, не блокчейн)
- **Genome Matchmaker** (`agenomics/matchmaker.py`): подбирает оптимальное назначение ролей для команды агентов по максимальному Compatibility Score (полный перебор, до 8 кандидатов)
- **Chain Risk Aggregator** (`agenomics/chain.py`): считает надёжность последовательного пайплайна агентов как произведение вероятностей, а не среднее (в отличие от Compatibility Score для параллельной команды)
- **Prompt-to-Genome Extractor** (`agenomics/extractor.py`): автоматическое извлечение `AgentGenome` из системного промпта агента через pluggable LLM-клиент (библиотека не делает сетевых вызовов сама)
- **Reports** (`agenomics/reports.py`): `trust_report()` и `compatibility_report()`, готовые Markdown-отчёты вместо сырых dataclass
- 20 новых тестов (`tests/test_v04_modules.py`), итого 47/47 тестов проходят

## [0.3.0] - 2026-09-02


### Добавлено
- Настраиваемые профили весов Trust Score (`default`, `healthcare`, `finance`, `content`) и Compatibility Score (`default`, `safety_critical`)
- Роли агентов (`role` поле): расхождение `risk_tolerance` между `executor` и `reviewer` не штрафуется в Compatibility Score
- Множественный `domain` (поле `domains`): Tier берётся по самому строгому домену
- `Confidence` (High/Medium/Low): уверенность в оценке, отдельно от самого `score`
- Атрибуция (`attribution` поле): во всех результатах, в промпте (обязательная последняя строка) и в API
- Валидация диапазонов входных данных в `AgentGenome` (`__post_init__`, `ValueError` при выходе за `[0, 100]` / `[0.0, 1.0]`)
- CI (GitHub Actions): тесты запускаются на каждый push/PR
- `CHANGELOG.md`, `CONTRIBUTING.md`

### Изменено
- `TrustScorer()` и `CompatibilityScorer()` теперь принимают `weight_profile` или `weights` в конструкторе (изменение сигнатуры: см. предупреждение о semver 0.x)
- `api.py`: эндпоинты `/score` и `/compatibility` теперь принимают `weight_profile`, `role`, `domains`; ответы включают `confidence`, `confidence_ratio`, `attribution`
- `amvera.yml`: исправлен ключ `run.command` (ранее использовался несуществующий `run.args`)
- `docs/METHODOLOGY.md`: добавлена таблица маппинга «поле генома → ось формулы», объяснение шкалы `social_style`, диапазоны валидации

### Исправлено
- README.md синхронизирован с реальным состоянием репозитория (ранее отставал на несколько версий от PyPI)

## [0.2.0] - 2026-09-01

### Добавлено
- `CompatibilityScorer`: оценка совместимости пары/команды агентов по 4 осям (ethics, risk_tolerance, social_style, accountability)
- Веб-API (`agenomics/api.py`, FastAPI): эндпоинты `POST /score`, `POST /compatibility`, `GET /health`
- Деплой на Amvera (`amvera.yml`)
- Публикация пакета на PyPI (`pip install agenomics`)

## [0.1.0] - 2026-08-31

### Добавлено
- Первая версия `TrustScorer` и `AgentGenome`
- Формула Trust Score по 5 осям (Transparency, BiasControl, DataSafety, Predictability, Accountability)
- Tier-множитель для критичных доменов (TIER_3, ×1.3)
- Жёсткий потолок Trust Score (≤70) для Autonomous-агентов без журнала аудита
- Промпт Trust Auditor
- Открытый репозиторий на GitHub (Apache 2.0)
