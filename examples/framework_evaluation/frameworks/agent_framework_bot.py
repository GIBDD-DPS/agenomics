# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Microsoft Agent Framework (преемник Semantic Kernel и AutoGen).
Требует переменную окружения GROQ_API_KEY (тот же ключ, что у остальных шаблонов).
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "agent-framework-core"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # задача с проверяемым ответом
CI_TIER = "experimental"  # новый шаблон: experimental, пока не доказал стабильность в CI


def run():
    import asyncio
    import os
    from agent_framework import Agent
    from agent_framework.openai import OpenAIChatCompletionClient

    client = OpenAIChatCompletionClient(
        model="openai/gpt-oss-20b",
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url=os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1"),
    )
    agent = Agent(client=client, instructions="You are a helpful assistant.")
    result = asyncio.run(agent.run("Сколько будет 144 разделить на 12 и умножить на 7? Ответь одним числом."))
    print(result.text)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 144 / 12 * 7 = 84. Проверяется текст ответа (AgentResponse.text)."""
    import re
    text = getattr(result, "text", None)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)84(?!\d)", text) is not None
