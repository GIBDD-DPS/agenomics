# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под CAMEL-AI (ChatAgent) на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "camel-ai"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from camel.agents import ChatAgent
    from camel.configs import GroqConfig
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    model = ModelFactory.create(
        model_platform=ModelPlatformType.GROQ,
        model_type=ctx.model,  # строка, не устаревший enum
        model_config_dict=GroqConfig(temperature=0.2).as_dict(),
        api_key=ctx.api_key,
        url=ctx.base_url,
    )
    agent = ChatAgent(system_message=ctx.system, model=model)
    response = agent.step(ctx.prompt)
    print(response.msgs[0].content)
    return response


def answer(result) -> str:
    """Первое сообщение ответа (msgs[0].content)."""
    msgs = getattr(result, "msgs", None) or []
    text = getattr(msgs[0], "content", None) if msgs else None
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
