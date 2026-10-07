# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Strands Agents на Groq через LiteLLM.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "strands-agents"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from strands import Agent
    from strands.models.litellm import LiteLLMModel

    # адрес Groq через litellm: GROQ_API_BASE
    agent = Agent(
        model=LiteLLMModel(model_id=ctx.litellm_model),
        system_prompt=ctx.system,
        callback_handler=None,  # без потокового вывода в консоль
    )
    result = agent(ctx.prompt)
    print(result)
    return result


def answer(result) -> str:
    """Текстовые блоки итогового сообщения ассистента."""
    message = getattr(result, "message", None)
    if not isinstance(message, dict):
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return "".join(block.get("text", "") for block in message.get("content", []))
