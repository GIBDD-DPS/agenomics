# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
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
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "atomic-agents"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте
DISABLED = "import_error в каждом прогоне CI (конфликт instructor/jiter с остальными фреймворками), 0% надёжности"  # v0.9.5: прогоны не запускаются, история сохраняется


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

    response = agent.run(BasicChatInputSchema(chat_message="У Ивана 3 пачки по 12 тетрадей. Он раздал 7 тетрадей. Сколько тетрадей у него осталось? Ответь одним числом."))
    print(response.chat_message)
    return response


def check(result) -> bool:
    """Задача с однозначным ответом: 3 * 12 - 7 = 29. Проверяется поле chat_message ответа."""
    import re
    text = getattr(result, "chat_message", None)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)29(?!\d)", text) is not None
