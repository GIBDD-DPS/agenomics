"""
Шаблон под BeeAI Framework (IBM Research, Linux Foundation AI),
переведён на Groq (бесплатный провайдер). BeeAI делегирует вызовы
модели через litellm под капотом, тот же формат строки, что и в
CrewAI/DSPy/Swarms. Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import asyncio
    from beeai_framework.agents.react import ReActAgent
    from beeai_framework.backend import ChatModel, ChatModelParameters
    from beeai_framework.memory import UnconstrainedMemory

    async def _run():
        llm = ChatModel.from_name(
            "groq:openai/gpt-oss-20b",
            ChatModelParameters(temperature=0.3),
        )
        agent = ReActAgent(llm=llm, tools=[], memory=UnconstrainedMemory())
        response = await agent.run("Что такое BeeAI Framework?")  # замените на вашу реальную задачу
        return response

    result = asyncio.run(_run())
    print(result.result.text if hasattr(result, "result") else result)
    return result
