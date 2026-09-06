"""
Шаблон под Haystack (deepset), Agent-компонент, Haystack 3.0, 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from haystack.components.agents import Agent
    from haystack.components.generators.chat import OpenAIChatGenerator
    from haystack.dataclasses import ChatMessage

    agent = Agent(
        chat_generator=OpenAIChatGenerator(model="gpt-4o-mini"),  # замените на вашу модель
        system_prompt="You are a helpful assistant.",
        tools=[],  # замените на ваши реальные инструменты
    )

    response = agent.run(messages=[ChatMessage.from_user("Что такое Haystack?")])
    print(response["last_message"].text)
    return response
