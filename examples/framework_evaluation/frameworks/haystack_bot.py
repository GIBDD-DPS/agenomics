# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Haystack, переведён на Groq (бесплатный провайдер, через
OpenAI-совместимый эндпоинт api.groq.com). Требует GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "haystack-ai"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from haystack.components.agents import Agent
    from haystack.components.generators.chat import OpenAIChatGenerator
    from haystack.dataclasses import ChatMessage
    from haystack.utils import Secret

    agent = Agent(
        chat_generator=OpenAIChatGenerator(
            api_key=Secret.from_env_var("GROQ_API_KEY"),
            api_base_url="https://api.groq.com/openai/v1",
            model="openai/gpt-oss-20b",
        ),
        system_prompt="You are a helpful assistant.",
        tools=[],
    )

    response = agent.run(messages=[ChatMessage.from_user("В школе 7 классов, в каждом по 28 учеников. Сколько всего учеников? Ответь одним числом.")])
    print(response["last_message"].text)
    return response


def check(result) -> bool:
    """Задача с однозначным ответом: 7 * 28 = 196. Проверяется последнее сообщение агента (last_message.text)."""
    import re
    text = getattr(result.get("last_message"), "text", None) if isinstance(result, dict) else None
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)196(?!\d)", text) is not None
