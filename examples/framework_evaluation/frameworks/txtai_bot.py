"""
Шаблон под txtai (NeuML), переведён на Groq (бесплатный провайдер, через
litellm-стиль строки модели, унаследованный от smolagents под капотом).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from txtai import Agent

    def today() -> str:
        """Gets the current date and time."""
        from datetime import datetime
        return datetime.today().isoformat()

    agent = Agent(
        model="groq/llama-3.3-70b-versatile",
        tools=[today, "websearch"],
        max_iterations=5,
    )

    result = agent("Что такое txtai в двух предложениях?")
    print(result)
    return result
