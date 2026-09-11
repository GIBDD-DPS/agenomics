"""
Шаблон под Swarms (kyegomez/swarms), переведён на Groq (бесплатный
провайдер, без карты). Требует переменную окружения GROQ_API_KEY.

Не путать с устаревшим OpenAI Swarm (deprecated с марта 2025, заменён
на OpenAI Agents SDK) - это отдельный, самостоятельный, активно
развивающийся проект с собственной архитектурой.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from swarms import Agent

    agent = Agent(
        agent_name="Assistant",
        system_prompt="You are a helpful assistant.",
        model_name="groq/openai/gpt-oss-20b",  # тот же формат litellm-строки, что и в CrewAI/DSPy
        max_loops=1,
    )

    result = agent.run("Что такое Swarms в двух предложениях?")  # замените на вашу реальную задачу
    print(result)
    return result
