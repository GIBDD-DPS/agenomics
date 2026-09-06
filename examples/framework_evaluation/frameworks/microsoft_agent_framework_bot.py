"""
Шаблон под Microsoft Agent Framework (MAF), проверено по актуальной документации, 2026.

Заменяет изначально предложенный OpenAI Swarm - он официально deprecated
с марта 2025 года (заменён на OpenAI Agents SDK, который уже есть отдельным
шаблоном). MAF - официальный преемник AutoGen и Semantic Kernel в Microsoft,
оба предшественника теперь в maintenance mode.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import asyncio
    from agent_framework import ChatAgent
    from agent_framework.openai import OpenAIChatClient

    async def _run():
        agent = ChatAgent(
            chat_client=OpenAIChatClient(model_id="gpt-4o-mini"),  # замените на вашу модель
            instructions="You are a helpful assistant.",
        )
        response = await agent.run("Что такое Microsoft Agent Framework?")  # замените на вашу реальную задачу
        return response

    result = asyncio.run(_run())
    print(result)
    return result
