# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под OpenAI Agents SDK, переведён на Groq (бесплатный провайдер,
через OpenAI-совместимый эндпоинт, тот же приём, что для Haystack/
Griptape/Semantic Kernel). Официально подтверждено документацией SDK:
OpenAIChatCompletionsModel принимает готовый AsyncOpenAI-клиент с любым
base_url. Требует GROQ_API_KEY.

Был в исходном списке из 14 фреймворков, убран при сокращении до 15 как
"слишком привязанный к OpenAI". Оказалось, это не так - официальный
путь для сторонних провайдеров есть, просто не был известен на тот
момент.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "openai-agents"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    import os
    from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, set_tracing_disabled

    set_tracing_disabled(disabled=True)  # трейсинг по умолчанию шлёт данные в OpenAI, не нужно для Groq

    groq_client = AsyncOpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    model = OpenAIChatCompletionsModel(model="openai/gpt-oss-20b", openai_client=groq_client)

    agent = Agent(name="Assistant", instructions="You are a helpful assistant.", model=model)

    result = Runner.run_sync(agent, "Сколько секунд в 17 минутах? Ответь одним числом.")
    print(result.final_output)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 17 * 60 = 1020. Проверяется итоговый ответ (final_output)."""
    import re
    text = getattr(result, "final_output", None)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)1020(?!\d)", text) is not None
