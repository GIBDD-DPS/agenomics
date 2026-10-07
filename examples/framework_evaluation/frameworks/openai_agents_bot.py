# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под OpenAI Agents SDK, OpenAI-совместимая модель на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "openai-agents"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, set_tracing_disabled

    set_tracing_disabled(disabled=True)  # трейсинг по умолчанию шлёт данные в OpenAI, не нужно для Groq
    client = AsyncOpenAI(api_key=ctx.api_key, base_url=ctx.base_url)
    model = OpenAIChatCompletionsModel(model=ctx.model, openai_client=client)
    agent = Agent(name="Assistant", instructions=ctx.system, model=model)
    result = Runner.run_sync(agent, ctx.prompt)
    print(result.final_output)
    return result


def answer(result) -> str:
    """Итоговый ответ (final_output)."""
    text = getattr(result, "final_output", None)
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
