# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Pydantic AI на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "pydantic-ai"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from pydantic_ai import Agent

    # провайдер Groq берёт адрес из GROQ_BASE_URL (корень, без /openai/v1)
    agent = Agent(ctx.prefixed_model, instructions=ctx.system)
    result = agent.run_sync(ctx.prompt)
    print(result.output)
    return result


def answer(result) -> str:
    """Итоговый ответ (output)."""
    text = getattr(result, "output", None)
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
