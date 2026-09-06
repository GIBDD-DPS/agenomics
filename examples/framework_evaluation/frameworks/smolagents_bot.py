"""
Шаблон под smolagents (Hugging Face), проверено по актуальной документации, 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from smolagents import CodeAgent, InferenceClientModel

    model = InferenceClientModel()  # использует Hugging Face Inference API по умолчанию
    agent = CodeAgent(tools=[], model=model)

    result = agent.run("Посчитай сумму чисел от 1 до 10")  # замените на вашу реальную задачу
    print(result)
    return result
