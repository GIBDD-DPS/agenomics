# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под BeeAI Framework (ReActAgent) на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "beeai-framework"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    import asyncio
    from beeai_framework.agents.react import ReActAgent
    from beeai_framework.backend import ChatModel, ChatModelParameters
    from beeai_framework.memory import UnconstrainedMemory

    async def _run():
        # адрес Groq через litellm: GROQ_API_BASE
        llm = ChatModel.from_name(ctx.prefixed_model, ChatModelParameters(temperature=0.3))
        agent = ReActAgent(llm=llm, tools=[], memory=UnconstrainedMemory())
        return await agent.run(ctx.prompt)

    result = asyncio.run(_run())
    print(result.result.text if hasattr(result, "result") else result)
    return result


def answer(result) -> str:
    """Итоговый ответ агента (result.text или last_message.text)."""
    message = getattr(result, "result", None) or getattr(result, "last_message", None)
    text = getattr(message, "text", None)
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
