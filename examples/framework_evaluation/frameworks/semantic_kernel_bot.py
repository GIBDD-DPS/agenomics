# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Semantic Kernel, переведён на Groq (бесплатный провайдер,
через OpenAI-совместимый эндпоинт, тот же приём, что для Haystack/
Griptape). Официального Groq-коннектора у Semantic Kernel нет, но
OpenAIChatCompletion принимает готовый AsyncOpenAI-клиент с любым
base_url через параметр async_client. Требует GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "semantic-kernel"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


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

        response = await agent.get_response(messages="Сколько дней в сумме в январе, феврале и марте невисокосного года? Ответь одним числом.")
        return response

    result = asyncio.run(_run())
    print(result)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 31 + 28 + 31 = 90. Проверяется содержимое ответа агента (response.content)."""
    import re
    text = getattr(result, "content", result)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)90(?!\d)", text) is not None
