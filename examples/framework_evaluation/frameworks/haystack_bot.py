"""
Шаблон под Haystack, переведён на Groq (бесплатный провайдер, через
OpenAI-совместимый эндпоинт api.groq.com). Требует GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from haystack.components.agents import Agent
    from haystack.components.generators.chat import OpenAIChatGenerator
    from haystack.dataclasses import ChatMessage
    from haystack.utils import Secret

    agent = Agent(
        chat_generator=OpenAIChatGenerator(
            api_key=Secret.from_env_var("GROQ_API_KEY"),
            api_base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
        ),
        system_prompt="You are a helpful assistant.",
        tools=[],
    )

    response = agent.run(messages=[ChatMessage.from_user("Что такое Haystack?")])
    print(response["last_message"].text)
    return response
