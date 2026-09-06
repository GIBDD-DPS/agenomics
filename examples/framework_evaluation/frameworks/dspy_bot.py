"""
Шаблон под DSPy (Stanford), ReAct-агент, проверено по актуальной документации, 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import dspy

    dspy.configure(lm=dspy.LM("openai/gpt-4o-mini"))  # замените на вашу модель

    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"The weather in {city} is sunny and 22C"

    agent = dspy.ReAct(
        signature="question -> answer",
        tools=[get_weather],  # замените на ваши реальные инструменты
        max_iters=5,
    )

    result = agent(question="Какая погода в Париже?")  # замените на вашу реальную задачу
    print(result.answer)
    return result
