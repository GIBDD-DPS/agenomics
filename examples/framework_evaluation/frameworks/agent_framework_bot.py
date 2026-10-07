# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Microsoft Agent Framework, OpenAI-совместимый клиент на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "agent-framework-core"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    import asyncio
    from agent_framework import Agent
    from agent_framework.openai import OpenAIChatCompletionClient

    client = OpenAIChatCompletionClient(model=ctx.model, api_key=ctx.api_key, base_url=ctx.base_url)
    agent = Agent(client=client, instructions=ctx.system)
    result = asyncio.run(agent.run(ctx.prompt))
    print(result.text)
    return result


def answer(result) -> str:
    """Текст ответа агента (AgentResponse.text)."""
    text = getattr(result, "text", None)
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
