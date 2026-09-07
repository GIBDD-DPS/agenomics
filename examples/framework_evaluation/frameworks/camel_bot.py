"""
Шаблон под CAMEL-AI, переведён на Groq (бесплатный провайдер).
Синтаксис подтверждён официальной документацией docs.camel-ai.org.
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from camel.agents import ChatAgent
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType
    from camel.configs import GroqConfig

    model = ModelFactory.create(
        model_platform=ModelPlatformType.GROQ,
        model_type=ModelType.GROQ_LLAMA_3_3_70B,
        model_config_dict=GroqConfig(temperature=0.2).as_dict(),
    )

    agent = ChatAgent(model=model)

    response = agent.step("Что такое CAMEL-AI?")
    print(response.msgs[0].content)
    return response
