# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Griptape, OpenAI-совместимый драйвер на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "griptape"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from griptape.artifacts import ErrorArtifact
    from griptape.drivers.prompt.openai import OpenAiChatPromptDriver
    from griptape.rules import Rule
    from griptape.structures import Agent

    agent = Agent(
        prompt_driver=OpenAiChatPromptDriver(model=ctx.model, api_key=ctx.api_key, base_url=ctx.base_url),
        rules=[Rule(ctx.system)],
    )
    agent.run(ctx.prompt)
    print("Answer:", agent.output)
    # [v0.9.5] Griptape не бросает исключение при ошибке провайдера (нет
    # сети, 401, 429), а кладёт её в ErrorArtifact. Без этой проверки сбой
    # прогона записывался бы как неверный ответ агента (task_failure), а не
    # как ошибка выполнения, и не классифицировался бы по причине.
    if isinstance(agent.output, ErrorArtifact):
        raise agent.output.exception or RuntimeError(agent.output.value)
    return agent.output


def answer(result) -> str:
    """Значение итогового артефакта (output.value)."""
    text = getattr(result, "value", result)
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
