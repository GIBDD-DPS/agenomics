"""
Шаблон под OpenAI Agents SDK (пакет openai-agents, проверено 2026).
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from agents import Agent, Runner

    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant",  # замените под вашу задачу
    )

    result = Runner.run_sync(agent, "Расскажи, что такое agentic AI, в двух предложениях")
    print(result.final_output)
    return result
