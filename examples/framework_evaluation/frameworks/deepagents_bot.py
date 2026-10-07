# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Deep Agents (LangChain) на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "deepagents"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from deepagents import create_deep_agent

    # ChatGroq берёт адрес из GROQ_BASE_URL (корень, без /openai/v1)
    agent = create_deep_agent(model=ctx.prefixed_model, system_prompt=ctx.system)
    result = agent.invoke({"messages": [{"role": "user", "content": ctx.prompt}]})
    print(result["messages"][-1].content)
    return result


def answer(result) -> str:
    """Последнее сообщение (ответ модели), не история с выводом инструментов."""
    messages = result.get("messages") if isinstance(result, dict) else None
    text = getattr(messages[-1], "content", None) if messages else None
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
