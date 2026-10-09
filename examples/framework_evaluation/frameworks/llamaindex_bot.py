# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под LlamaIndex (FunctionAgent) на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "llama-index-core"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    import asyncio
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.tools import FunctionTool
    from llama_index.llms.groq import Groq

    def current_date() -> str:
        """Return today's date (ISO format)."""
        import datetime
        return datetime.date.today().isoformat()

    async def _run():
        # Один нейтральный инструмент, к задачам не относящийся: с пустым
        # списком FunctionAgent отправляет "tool_choice": null, и Groq
        # отвечает 400 (прогоны 119-125 после перехода на run(ctx)).
        agent = FunctionAgent(
            tools=[FunctionTool.from_defaults(fn=current_date)],
            llm=Groq(model=ctx.model, api_key=ctx.api_key, api_base=ctx.base_url),
            system_prompt=ctx.system,
        )
        return await agent.run(ctx.prompt)

    result = asyncio.run(_run())
    print(result)
    return result


def answer(result) -> str:
    """Ответ агента (result.response.content), не вывод инструментов.
    Сообщение есть, а текста нет (так LlamaIndex отвечает, проглотив битый
    ответ модели): это пустой ответ, то есть провал задачи. Нет самого
    сообщения: форма результата не та, исход неизвестен."""
    response = getattr(result, "response", None)
    if response is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(getattr(response, "content", None) or "")
