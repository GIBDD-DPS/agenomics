"""
Шаблон под Atomic Agents, проверено по актуальной документации (v2.10.x), 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import instructor
    from openai import OpenAI
    from atomic_agents import AtomicAgent, AgentConfig, BasicChatInputSchema, BaseIOSchema
    from atomic_agents.context import SystemPromptGenerator, ChatHistory
    from pydantic import Field

    class CustomOutputSchema(BaseIOSchema):
        """Ответ агента с сообщением."""
        chat_message: str = Field(..., description="Ответ агента пользователю.")

    system_prompt_generator = SystemPromptGenerator(
        background=["Ты полезный ассистент."],
    )

    client = instructor.from_openai(OpenAI())  # замените на вашу модель/провайдера

    agent = AtomicAgent[BasicChatInputSchema, CustomOutputSchema](
        config=AgentConfig(
            client=client,
            model="gpt-4o-mini",
            system_prompt_generator=system_prompt_generator,
            history=ChatHistory(),
        )
    )

    response = agent.run(BasicChatInputSchema(chat_message="Что такое Atomic Agents?"))  # замените на вашу задачу
    print(response.chat_message)
    return response
