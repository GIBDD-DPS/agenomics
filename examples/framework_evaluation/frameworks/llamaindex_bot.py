"""
Шаблон под LlamaIndex, переведён на Groq (бесплатный провайдер).
Требует пакет llama-index-llms-groq и переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


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
            llm=Groq(model="llama-3.3-70b-versatile"),
            system_prompt="You are a helpful AI assistant.",
        )
        response = await agent.run("Какая погода в Париже?")
        return response

    result = asyncio.run(_run())
    print(result)
    return result
