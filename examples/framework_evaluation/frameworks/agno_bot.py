"""
Шаблон под Agno (бывший Phidata), переведён на Groq (бесплатный провайдер).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from agno.agent import Agent
    from agno.models.groq import Groq

    agent = Agent(
        model=Groq(id="llama-3.3-70b-versatile"),
        description="You are a helpful assistant.",
        markdown=True,
    )

    agent.print_response("Что такое Agno в двух предложениях?")
    return agent
