"""
Шаблон под LlamaIndex, переведён на Groq (бесплатный провайдер).
Требует пакет llama-index-llms-groq и переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "llama-index-core"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    import asyncio
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.tools import FunctionTool
    from llama_index.llms.groq import Groq

    def get_weather(location: str) -> str:
        """Get the weather for a given location."""
        return f"The weather in {location} is cloudy with a high of 15C."

    async def _run():
        agent = FunctionAgent(
            tools=[FunctionTool.from_defaults(fn=get_weather)],
            llm=Groq(model="openai/gpt-oss-20b"),
            system_prompt="You are a helpful AI assistant.",
        )
        response = await agent.run("Какая погода в Париже?")
        return response

    result = asyncio.run(_run())
    print(result)
    return result


def check(result) -> bool:
    """Инструмент get_weather возвращает "cloudy with a high of 15C":
    правильный ответ обязан содержать 15. Проверяется ответ агента
    (result.response.content), а не вывод инструмента."""
    import re
    response = getattr(result, "response", None)
    text = getattr(response, "content", None) if response is not None else None
    return re.search(r"(?<!\d)15(?!\d)", str(text or "")) is not None
