"""
Шаблон под CAMEL-AI, переведён на Groq (бесплатный провайдер).
Требует переменную окружения GROQ_API_KEY.

ВАЖНО: список enum ModelType.GROQ_* в CAMEL сам устарел (там только
уже снятые с производства модели вроде llama-3.3-70b). CAMEL поддерживает
произвольную строку в model_type в обход enum. Используем этот путь.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from camel.agents import ChatAgent
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    from camel.configs import GroqConfig

    model = ModelFactory.create(
        model_platform=ModelPlatformType.GROQ,
        model_type="openai/gpt-oss-20b",  # строка, не устаревший enum
        model_config_dict=GroqConfig(temperature=0.2).as_dict(),
    )

    agent = ChatAgent(model=model)

    response = agent.step("Что такое CAMEL-AI?")
    print(response.msgs[0].content)
    return response
