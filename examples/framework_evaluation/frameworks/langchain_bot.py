"""
Шаблон под LangChain, переведён на Groq (бесплатный провайдер, без карты).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from langchain.agents import create_agent

    def get_weather(city: str) -> str:
        """Get weather for a given city."""
        return f"It's always sunny in {city}!"

    agent = create_agent(
        model="groq:openai/gpt-oss-20b",
        tools=[get_weather],
        system_prompt="You are a helpful assistant",
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Какая погода в Сан-Франциско?"}]}
    )
    print(result["messages"][-1].content)
    return result
