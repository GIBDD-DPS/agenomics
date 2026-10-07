# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Agno (бывший Phidata) на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "agno"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from agno.agent import Agent
    from agno.models.groq import Groq

    # SDK Groq берёт адрес из GROQ_BASE_URL (корень, без /openai/v1)
    agent = Agent(model=Groq(id=ctx.model, api_key=ctx.api_key), description=ctx.system, markdown=True)
    response = agent.run(ctx.prompt)
    print(response.content)
    # [v0.9.5] Agno не бросает исключение при ошибке провайдера (нет сети,
    # 401, 429): RunOutput получает status=ERROR, а текст ошибки попадает в
    # content. Без этой проверки сбой прогона записывался бы как неверный
    # ответ агента (task_failure), а не как ошибка выполнения.
    if getattr(getattr(response, "status", None), "value", None) == "ERROR":
        raise RuntimeError(f"agno RunStatus.ERROR: {response.content}")
    return response


def answer(result) -> str:
    """Текст ответа (RunOutput.content)."""
    text = getattr(result, "content", None)
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
