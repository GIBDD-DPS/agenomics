# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под AG2 (AutoGen) на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "autogen"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from autogen import ConversableAgent, LLMConfig

    # клиент Groq берёт адрес из GROQ_BASE_URL (корень, без /openai/v1)
    llm_config = LLMConfig({"api_type": "groq", "model": ctx.model, "api_key": ctx.api_key})
    agent = ConversableAgent(name="assistant", system_message=ctx.system, llm_config=llm_config)
    response = agent.run(message=ctx.prompt, max_turns=1)
    response.process()
    return response


def answer(result) -> str:
    """Итог диалога (summary), иначе последнее сообщение."""
    text = getattr(result, "summary", None)
    if not text:
        messages = list(getattr(result, "messages", None) or [])
        text = messages[-1].get("content") if messages and isinstance(messages[-1], dict) else None
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
