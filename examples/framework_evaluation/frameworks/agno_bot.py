"""
Шаблон под Agno (бывший Phidata), проверено по актуальной документации, 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    agent = Agent(
        model=OpenAIChat(id="gpt-4o-mini"),  # замените на вашу модель
        description="You are a helpful assistant.",
        markdown=True,
    )

    agent.print_response("Что такое Agno в двух предложениях?")  # замените на вашу реальную задачу
    return agent
