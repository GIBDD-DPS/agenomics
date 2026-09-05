"""
capture_log_v2.py — исправленная версия сборщика логов из 14 фреймворков.

Автор: Dm.Andreyanov / доработка для интеграции с Agenomics AEP-001
Проект: Prizolov Lab

Исправлено 4 реальных бага оригинального скрипта:
1. Падение run_fn() обрывало сбор ЦЕЛИКОМ — теперь падение одного
   фреймворка не мешает остальным 13, и само падение записывается
   как данные (это же реальный Incident!), а не теряется.
2. logging-хендлер не снимался при исключении — утечка обработчика
   на logger'е, растущая с каждым упавшим фреймворком.
3. Не было timestamp/duration — без них невозможно восстановить,
   КОГДА и КАК ДОЛГО шёл прогон, что нужно для AEP-001 Observation.
4. Не фиксировался статус (успех/ошибка) отдельным полем — приходилось
   бы парсить result/raw_log эвристически, чтобы понять, упал ли агент.
"""

import contextlib
import io
import json
import logging
import time
import traceback
from datetime import datetime, timezone

LOG_FILE = "agent_logs_library.jsonl"


def capture_log(framework: str, run_fn, **kwargs):
    """
    Запускает агента и перехватывает логи в файл — теперь безопасно:
    падение run_fn() не прерывает сбор остальных фреймворков и само
    становится частью записи (status="error" + traceback), а не тихо
    теряется или обрывает весь скрипт.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: без Formatter StreamHandler пишет ТОЛЬКО текст
    # сообщения, без уровня (WARNING/ERROR) — эвристический поиск этих
    # слов в raw_log (import_to_agenomics.py) иначе никогда не сработает,
    # даже если реальный logging.warning()/error() был вызван. Найдено
    # при тестировании: logging.warning("Rate limit...") давал в raw_log
    # просто "Rate limit...", без единого шанса на обнаружение по тексту.
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    loggers = kwargs.get("loggers", [""])

    for logger_name in loggers:
        logging.getLogger(logger_name).addHandler(handler)
        logging.getLogger(logger_name).setLevel(logging.DEBUG)

    started_at = datetime.now(timezone.utc)
    start_perf = time.perf_counter()
    status = "success"
    result_str = ""
    error_str = None

    try:
        with contextlib.redirect_stdout(stream):
            result = run_fn()
        result_str = str(result)[:500]
    except Exception:
        # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: падение не пробрасывается наружу —
        # иначе оно оборвало бы сбор для всех оставшихся фреймворков.
        status = "error"
        error_str = traceback.format_exc()
        result_str = ""
    finally:
        # КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: хендлеры снимаются ВСЕГДА, даже при
        # исключении — иначе они накапливаются на logger'е с каждым
        # упавшим фреймворком (утечка, растущая линейно с числом падений).
        for logger_name in loggers:
            logging.getLogger(logger_name).removeHandler(handler)

    duration_seconds = round(time.perf_counter() - start_perf, 3)

    entry = {
        "framework": framework,
        "timestamp": started_at.isoformat(),
        "duration_seconds": duration_seconds,
        "status": status,
        "raw_log": stream.getvalue(),
        "result": result_str,
        "error": error_str,  # None при успехе, полный traceback при падении
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return status  # можно проверять в вызывающем коде, не обязательно


def capture_all(framework_runs: dict, **kwargs):
    """
    Удобный раннер поверх capture_log() для всех 14 фреймворков разом:
    framework_runs = {"langchain": run_langchain, "autogen": run_autogen, ...}

    Возвращает сводку {framework: status} — сразу видно, сколько из 14
    реально отработали, без необходимости парсить JSONL вручную.
    """
    summary = {}
    for framework, run_fn in framework_runs.items():
        summary[framework] = capture_log(framework, run_fn, **kwargs)
    return summary
