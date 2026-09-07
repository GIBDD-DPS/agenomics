"""
Шаблон под Atomic Agents, переведён на Groq (бесплатный провайдер, через
instructor.from_groq()). Требует пакет groq и переменную GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import instructor
    from groq import Groq
    from atomic_agents import AtomicAgent, AgentConfig, BasicChatInputSchema, BaseIOSchema
    from atomic_agents.context import SystemPromptGenerator, ChatHistory
    from pydantic import Field

    class CustomOutputSchema(BaseIOSchema):
        """Ответ агента с сообщением."""
        chat_message: str = Field(..., description="Ответ агента пользователю.")

    system_prompt_generator = SystemPromptGenerator(
        background=["Ты полезный ассистент."],
    )

    client = instructor.from_groq(Groq())

    agent = AtomicAgent[BasicChatInputSchema, CustomOutputSchema](
        config=AgentConfig(
            client=client,
            model="llama-3.3-70b-versatile",
            system_prompt_generator=system_prompt_generator,
            history=ChatHistory(),
        )
    )

    response = agent.run(BasicChatInputSchema(chat_message="Что такое Atomic Agents?"))
    print(response.chat_message)
    return response
