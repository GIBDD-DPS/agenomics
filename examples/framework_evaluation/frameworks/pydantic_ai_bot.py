"""
Шаблон под Pydantic AI, переведён на Groq (бесплатный провайдер).
Нативная поддержка подтверждена ai.pydantic.dev/api/models/groq.
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from pydantic_ai import Agent

    agent = Agent(
        "groq:openai/gpt-oss-20b",
        instructions="Be concise, reply with one sentence.",
    )

    result = agent.run_sync("Что такое Pydantic AI?")
    print(result.output)
    return result
