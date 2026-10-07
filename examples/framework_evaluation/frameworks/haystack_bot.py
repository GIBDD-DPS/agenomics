# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Haystack (Agent), OpenAI-совместимый генератор на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "haystack-ai"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from haystack.components.agents import Agent
    from haystack.components.generators.chat import OpenAIChatGenerator
    from haystack.dataclasses import ChatMessage
    from haystack.utils import Secret

    agent = Agent(
        chat_generator=OpenAIChatGenerator(
            api_key=Secret.from_env_var("GROQ_API_KEY"), api_base_url=ctx.base_url, model=ctx.model,
        ),
        system_prompt=ctx.system,
        tools=[],
    )
    response = agent.run(messages=[ChatMessage.from_user(ctx.prompt)])
    print(response["last_message"].text)
    return response


def answer(result) -> str:
    """Текст последнего сообщения (last_message.text)."""
    text = getattr(result.get("last_message"), "text", None) if isinstance(result, dict) else None
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
