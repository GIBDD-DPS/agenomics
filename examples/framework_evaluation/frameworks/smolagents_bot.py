"""
Шаблон под smolagents (Hugging Face). Уже использует бесплатный провайдер
по умолчанию (InferenceClientModel -> Hugging Face Inference API),
изменений не требовалось.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from smolagents import CodeAgent, InferenceClientModel

    model = InferenceClientModel()
    agent = CodeAgent(tools=[], model=model)

    result = agent.run("Посчитай сумму чисел от 1 до 10")
    print(result)
    return result
