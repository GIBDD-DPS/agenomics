# Agenomics 0.9.3 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Haystack, переведён на Groq (бесплатный провайдер, через
OpenAI-совместимый эндпоинт api.groq.com). Требует GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "haystack-ai"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from haystack.components.agents import Agent
    from haystack.components.generators.chat import OpenAIChatGenerator
    from haystack.dataclasses import ChatMessage
    from haystack.utils import Secret

    agent = Agent(
        chat_generator=OpenAIChatGenerator(
            api_key=Secret.from_env_var("GROQ_API_KEY"),
            api_base_url="https://api.groq.com/openai/v1",
            model="openai/gpt-oss-20b",
        ),
        system_prompt="You are a helpful assistant.",
        tools=[],
    )

    response = agent.run(messages=[ChatMessage.from_user("Что такое Haystack?")])
    print(response["last_message"].text)
    return response
