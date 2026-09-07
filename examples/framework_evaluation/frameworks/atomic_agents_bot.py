"""
Шаблон под Atomic Agents, переведён на Groq (бесплатный провайдер, через
instructor.from_groq()). Требует пакет groq и переменную GROQ_API_KEY.

НЕОБЪЯСНЁННАЯ НАХОДКА: в реальном прогоне CI импорт падал с
"ImportError: cannot import name 'AtomicAgent' from 'atomic_agents'",
хотя именно такой импорт указан в официальной документации PyPI на
момент проверки. Возможная причина - конфликт версий зависимостей при
установке 14 других фреймворков в то же окружение (например, версия
instructor/pydantic, которую требует один из соседних пакетов).
Если воспроизводится у вас - попробуйте установить atomic-agents в
изолированном окружении отдельно от остальных 14, чтобы проверить
гипотезу.
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
            model="openai/gpt-oss-20b",
            system_prompt_generator=system_prompt_generator,
            history=ChatHistory(),
        )
    )

    response = agent.run(BasicChatInputSchema(chat_message="Что такое Atomic Agents?"))
    print(response.chat_message)
    return response
