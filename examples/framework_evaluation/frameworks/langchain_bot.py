"""
Шаблон под LangChain (актуальный API create_agent, LangChain v1, 2026).
Задача-пример ("погода в Сан-Франциско") - замените на вашу реальную.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from langchain.agents import create_agent

    def get_weather(city: str) -> str:
        """Get weather for a given city."""
        return f"It's always sunny in {city}!"

    agent = create_agent(
        model="openai:gpt-4o-mini",  # замените на вашу модель
        tools=[get_weather],          # замените на ваши реальные инструменты
        system_prompt="You are a helpful assistant",
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Какая погода в Сан-Франциско?"}]}
    )
    print(result["messages"][-1].content)
    return result
