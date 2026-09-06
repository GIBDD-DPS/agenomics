"""
Шаблон под Strands Agents (AWS), проверено по актуальной документации, 2026.

Заменяет изначально предложенный ControlFlow (Prefect) - его репозиторий
переехал в prefect-archive/ControlFlow, то есть архивирован, а сам Prefect
рекомендует вместо него Marvin 3.0 (уже есть отдельным шаблоном). Strands
Agents - реальный, активно поддерживаемый SDK от AWS, закрывает пробел:
у нас пока не было ничего из AWS-экосистемы.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from strands import Agent, tool

    @tool
    def get_weather(location: str) -> str:
        """Get the weather for a given location."""
        return f"The weather in {location} is cloudy with a high of 15C."

    agent = Agent(tools=[get_weather])  # по умолчанию Amazon Bedrock, нужны AWS-креды

    result = agent("Какая погода в Париже?")  # замените на вашу реальную задачу
    print(result)
    return result
