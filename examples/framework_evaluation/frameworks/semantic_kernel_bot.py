"""
Шаблон под Semantic Kernel, переведён на Groq (бесплатный провайдер,
через OpenAI-совместимый эндпоинт, тот же приём, что для Haystack/
Griptape). Официального Groq-коннектора у Semantic Kernel нет, но
OpenAIChatCompletion принимает готовый AsyncOpenAI-клиент с любым
base_url через параметр async_client. Требует GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import os
    import asyncio
    from openai import AsyncOpenAI
    from semantic_kernel import Kernel
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
    from semantic_kernel.agents import ChatCompletionAgent

    async def _run():
        groq_client = AsyncOpenAI(
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )

        kernel = Kernel()
        kernel.add_service(OpenAIChatCompletion(
            ai_model_id="openai/gpt-oss-20b",
            async_client=groq_client,
        ))

        agent = ChatCompletionAgent(
            kernel=kernel,
            name="assistant",
            instructions="You are a helpful assistant.",
        )

        response = await agent.get_response(messages="Что такое Semantic Kernel?")  # замените на вашу задачу
        return response

    result = asyncio.run(_run())
    print(result)
    return result
