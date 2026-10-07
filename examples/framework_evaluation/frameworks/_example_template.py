# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон плагина фреймворка. Скопируйте этот файл в frameworks/<ваше_имя>.py
(БЕЗ ведущего подчёркивания — файлы с "_" в начале имени игнорируются
раннером, это позволяет держать в папке такие шаблоны/утилиты).

Обязательно: run(ctx), который строит агента вашего фреймворка и
вызывает его, и answer(result), который возвращает текст ИТОГОВОГО ответа
агента (не запрос и не вывод инструментов). Если форма результата не
та, что ожидалась, answer бросает ValueError: исход неизвестен, а не
провал агента.

Модель, задачу и адрес провайдера даёт раннер (conditions.RunContext):
ctx.model ("openai/gpt-oss-20b"), ctx.litellm_model ("groq/..."),
ctx.prefixed_model ("groq:..."), ctx.prompt, ctx.system, ctx.base_url
(OpenAI-совместимый адрес .../openai/v1), ctx.api_key. Модель и задачу в
шаблон не зашивайте: раннер меняет их по расписанию. Клиенты на SDK Groq
и litellm берут адрес из GROQ_BASE_URL и GROQ_API_BASE, раннер выставляет
их сам. Ответ проверяет задача, а не шаблон.

Опционально: DOMAIN, AUTONOMY (иначе используются значения по умолчанию),
FRAMEWORK_PACKAGE (pip-имя библиотеки, иначе framework_version не пишется),
CI_TIER ("required" или "experimental", по умолчанию "experimental").
"""

DOMAIN = "content"      # или "finance"/"support"/"health" и т.д. — см. docs/METHODOLOGY.md
AUTONOMY = "advisory"   # "advisory" или "autonomous"
FRAMEWORK_PACKAGE = "langchain"  # pip-имя библиотеки фреймворка, её версия пишется в EvidenceStore
CI_TIER = "experimental"  # новый шаблон experimental, пока не доказал стабильность в CI


def run(ctx):
    """Замените на реальный вызов вашего агента/фреймворка."""
    # from langchain.agents import create_agent
    # agent = create_agent(model=ctx.prefixed_model, tools=[], system_prompt=ctx.system)
    # return agent.invoke({"messages": [{"role": "user", "content": ctx.prompt}]})
    raise NotImplementedError("Скопируйте этот файл и замените run() на реальный вызов")


def answer(result) -> str:
    """Текст итогового ответа агента."""
    # return result["messages"][-1].content
    raise NotImplementedError("Скопируйте этот файл и реализуйте answer()")
