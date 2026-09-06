"""
Шаблон под Marvin (Prefect), проверено по актуальной документации, 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from marvin import Agent

    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant.",  # замените под вашу задачу
    )

    result = agent.run("Что такое Marvin в двух предложениях?")  # замените на вашу реальную задачу
    print(result)
    return result
