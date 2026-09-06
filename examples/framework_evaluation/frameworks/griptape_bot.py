"""
Шаблон под Griptape (проверено по актуальной документации, 2026).
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from griptape.drivers.prompt.openai import OpenAiChatPromptDriver
    from griptape.structures import Agent

    agent = Agent(
        prompt_driver=OpenAiChatPromptDriver(model="gpt-4o-mini"),  # замените на вашу модель
    )

    agent.run("Что такое Griptape в двух предложениях?")  # замените на вашу реальную задачу
    print("Answer:", agent.output)
    return agent.output
