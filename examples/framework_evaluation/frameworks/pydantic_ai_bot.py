"""
Шаблон под Pydantic AI, проверено по актуальной документации, 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from pydantic_ai import Agent

    agent = Agent(
        "openai:gpt-4o-mini",  # замените на вашу модель
        instructions="Be concise, reply with one sentence.",
    )

    result = agent.run_sync("Что такое Pydantic AI?")  # замените на вашу реальную задачу
    print(result.output)
    return result
