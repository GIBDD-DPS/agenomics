"""
Шаблон под PraisonAI, проверено по актуальной документации, 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from praisonaiagents import Agent

    agent = Agent(instructions="You are a helpful assistant.")  # замените под вашу задачу

    result = agent.start("Что такое PraisonAI в двух предложениях?")  # замените на вашу реальную задачу
    print(result)
    return result
