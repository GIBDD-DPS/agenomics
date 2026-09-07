"""
Шаблон под smolagents (Hugging Face).

Обновление: анонимный доступ к Hugging Face Inference API без токена
перестал работать в CI (реальная находка из логов: "You must provide
an api_key to work with auto API or log in with hf auth login").
Нужен бесплатный токен с huggingface.co/settings/tokens, положенный в
переменную окружения HF_TOKEN.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import os
    from smolagents import CodeAgent, InferenceClientModel

    model = InferenceClientModel(token=os.environ.get("HF_TOKEN"))
    agent = CodeAgent(tools=[], model=model)

    result = agent.run("Посчитай сумму чисел от 1 до 10")
    print(result)
    return result
