"""
Шаблон под Semantic Kernel (проверено по актуальной документации, 2026).
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import asyncio
    from semantic_kernel.agents import ChatCompletionAgent
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

    async def _run():
        agent = ChatCompletionAgent(
            service=OpenAIChatCompletion(ai_model_id="gpt-4o-mini"),  # замените на вашу модель
            name="assistant",
            instructions="You are a helpful assistant.",
        )
        response = await agent.get_response(messages="Объясни, что такое agentic AI простыми словами")
        return response

    result = asyncio.run(_run())
    print(result.content)
    return result
