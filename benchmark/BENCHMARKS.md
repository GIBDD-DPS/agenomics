# Agenomics Synthetic Benchmark — Published Results

**Автор**: Dm.Andreyanov · **Проект**: Prizolov Lab
**Версия бенчмарка**: v0.2 (соответствует коду agenomics v0.6.0)
**Дата прогона**: 2026-09-03

> Полная методология и честные ограничения — в [`README.md`](README.md).
> Этот файл — просто зафиксированный числовой результат конкретного
> прогона, пригодный для цитирования в README/статьях/презентациях как
> **Engineering Evidence**, а не как маркетинговое заявление.

## Итоговая таблица

| Метрика | Значение | Статус |
|---|---:|---|
| Reproducibility | **1.000** | ✅ computed |
| Behavioral Predictability (formula consistency) | **-1.000** | ✅ computed |
| Trust Calibration (formula consistency) | **0.996** | ✅ computed |
| Compatibility Accuracy (v0.1, n=4) | **1.000** | ✅ computed |
| Compatibility Accuracy v2 (n=270) | **1.000** | ✅ computed |
| Drift Detection Lag (v1, 3 сценария) | 3 шага в среднем; **mild не обнаружена** | ✅ computed |
| Drift Detection v2 (7 сценариев) | **1.000** (все проверки пройдены) | ✅ computed |
| Incident Correlation | — | ⛔ not_computable |

**Как читать**: computed = 7/8 метрик успешно вычислены на
синтетических данных. Incident Correlation остаётся честно
`not_computable` — не по недосмотру, а потому что синтетическая
имитация была бы циркулярной проверкой самой себя (см. `README.md`).
Инфраструктура для вычисления этой метрики на РЕАЛЬНЫХ данных теперь
существует — `agenomics.RealWorldEvaluationLayer` (v0.6.0).

## Что изменилось между v0.1 и v0.2 бенчмарка

| Область | v0.1 | v0.2 |
|---|---|---|
| Compatibility ground truth | 4 случая вручную | **270 случаев**, 9 систематических категорий |
| Drift detection | 3 уровня тяжести (mild/moderate/severe) на линейной эвристике v1 | **7 сценариев** (+ sudden, recovery, oscillation, no_drift) на `DriftMonitorV2` |
| Real-world инфраструктура | Не было | `RealWorldEvaluationLayer` — делает Incident Correlation вычислимой НА РЕАЛЬНЫХ данных |

## Ключевая находка v0.1 → как она исправлена в v0.2

**Находка (v0.1)**: `DriftMonitor` (v1) не обнаруживал mild-деградацию
вовсе за 15 шагов — задокументировано как реальное ограничение, не
скрыто.

**Исправление (v0.2)**: `DriftMonitorV2` с rolling window + EWMA +
явной классификацией тяжести обнаруживает mild-деградацию за разумное
окно (см. `Drift Detection v2`). Найдена и исправлена *новая* проблема,
обнаруженная при калибровке v2: колебания (oscillation) без тренда
изначально ложно классифицировались как `sudden`; исправлено через
подсчёт смен знака приращений, отличающий колебание от единичного
устойчивого скачка. Честный остаточный дефект: первые ~2 снимка
колебательного паттерна (до заполнения rolling window) всё ещё могут
классифицироваться неточно — это transient, не устранённый полностью,
и заявлять обратное было бы нечестно.

## Как воспроизвести эти цифры

```bash
git clone https://github.com/GIBDD-DPS/agenomics.git
cd agenomics
pip install -r requirements.txt
PYTHONPATH=. python3 -m benchmark.run_benchmark
```

Все сценарии детерминированы (без `random`) — при том же коде вы должны
получить **ровно те же числа**, что в таблице выше. Если нет — это
регрессия, о которой стоит сообщить через GitHub Issues.

## Ограничения, которые остаются в силе

Compatibility Accuracy v2 (n=270) — по-прежнему **синтетический**
ground truth, сконструированный вручную, не выборка реальных
конфликтов агентов. 270 случаев ощутимо надёжнее 4, но это всё ещё не
замена реальным данным — см. `docs/SPECIFICATION.md`, раздел 10.
