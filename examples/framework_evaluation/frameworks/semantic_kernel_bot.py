# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Semantic Kernel (ChatCompletionAgent), OpenAI-совместимый клиент на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "semantic-kernel"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    import asyncio
    from openai import AsyncOpenAI
    from semantic_kernel import Kernel
    from semantic_kernel.agents import ChatCompletionAgent
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

    async def _run():
        kernel = Kernel()
        kernel.add_service(OpenAIChatCompletion(
            ai_model_id=ctx.model, async_client=AsyncOpenAI(api_key=ctx.api_key, base_url=ctx.base_url),
        ))
        agent = ChatCompletionAgent(kernel=kernel, name="assistant", instructions=ctx.system)
        return await agent.get_response(messages=ctx.prompt)

    result = asyncio.run(_run())
    print(result)
    return result


def answer(result) -> str:
    """Содержимое ответа (content)."""
    text = getattr(result, "content", result)
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
