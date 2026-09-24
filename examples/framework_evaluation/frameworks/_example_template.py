"""
Шаблон плагина фреймворка. Скопируйте этот файл в frameworks/<ваше_имя>.py
(БЕЗ ведущего подчёркивания — файлы с "_" в начале имени игнорируются
раннером, это позволяет держать в папке такие шаблоны/утилиты).

Обязательно: функция run(), которая реально вызывает вашего агента.
Обязательно: MODEL_VERSION, провайдер и модель, которую реально вызывает
run() (например, "groq/openai/gpt-oss-20b"). Пишется в
EvidenceStore.model_version, чтобы смена модели не выглядела в истории
как дрейф самого агента.
Опционально: DOMAIN, AUTONOMY (иначе используются значения по умолчанию),
PROMPT_VERSION (если версионируете системный промпт).
"""

DOMAIN = "content"      # или "finance"/"support"/"health" и т.д. — см. docs/METHODOLOGY.md
AUTONOMY = "advisory"   # "advisory" или "autonomous"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # замените на реально вызываемую модель


def run():
    """Замените на реальный вызов вашего агента/фреймворка."""
    # from langchain.agents import ...
    # agent = ...
    # return agent.invoke("тестовая задача")
    raise NotImplementedError("Скопируйте этот файл и замените run() на реальный вызов")
