"""
Шаблон под CAMEL-AI (проверено по актуальной документации, 2026).
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from camel.agents import ChatAgent
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type=ModelType.GPT_4O_MINI,  # замените на вашу модель
    )

    agent = ChatAgent(model=model)  # добавьте system_message/tools под вашу задачу

    response = agent.step("Что такое CAMEL-AI?")
    print(response.msgs[0].content)
    return response
