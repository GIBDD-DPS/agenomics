# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Pydantic AI, переведён на Groq (бесплатный провайдер).
Нативная поддержка подтверждена ai.pydantic.dev/api/models/groq.
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "pydantic-ai"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from pydantic_ai import Agent

    agent = Agent(
        "groq:openai/gpt-oss-20b",
        instructions="Be concise, reply with one sentence.",
    )

    result = agent.run_sync("Сколько будет 23 умножить на 19? Ответь одним числом.")
    print(result.output)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 23 * 19 = 437. Проверяется итоговый ответ (result.output)."""
    import re
    text = getattr(result, "output", None)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)437(?!\d)", text) is not None
