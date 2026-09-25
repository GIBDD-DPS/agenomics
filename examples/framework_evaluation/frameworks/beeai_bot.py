# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под BeeAI Framework (IBM Research, Linux Foundation AI),
переведён на Groq (бесплатный провайдер). BeeAI делегирует вызовы
модели через litellm под капотом, тот же формат строки, что и в
CrewAI/DSPy/Swarms. Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "beeai-framework"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    import asyncio
    from beeai_framework.agents.react import ReActAgent
    from beeai_framework.backend import ChatModel, ChatModelParameters
    from beeai_framework.memory import UnconstrainedMemory

    async def _run():
        llm = ChatModel.from_name(
            "groq:openai/gpt-oss-20b",
            ChatModelParameters(temperature=0.3),
        )
        agent = ReActAgent(llm=llm, tools=[], memory=UnconstrainedMemory())
        response = await agent.run("Сколько минут в 3 часах и 25 минутах? Ответь одним числом.")
        return response

    result = asyncio.run(_run())
    print(result.result.text if hasattr(result, "result") else result)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 3 * 60 + 25 = 205. Проверяется итоговый ответ агента (result.text или last_message.text)."""
    import re
    answer = getattr(result, "result", None) or getattr(result, "last_message", None)
    text = getattr(answer, "text", None)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)205(?!\d)", text) is not None
