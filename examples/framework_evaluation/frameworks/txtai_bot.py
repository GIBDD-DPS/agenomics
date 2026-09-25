# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под txtai (NeuML), переведён на Groq (бесплатный провайдер, через
litellm-стиль строки модели, унаследованный от smolagents под капотом).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "txtai"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте
DISABLED = "rate_limit почти в каждом прогоне CI (7% надёжности): агент с websearch делает много запросов"  # v0.9.5: прогоны не запускаются, история сохраняется


def run():
    from txtai import Agent

    def today() -> str:
        """Gets the current date and time."""
        from datetime import datetime
        return datetime.today().isoformat()

    agent = Agent(
        model="groq/openai/gpt-oss-20b",
        tools=[today, "websearch"],
        max_iterations=5,
    )

    result = agent("Пятеро друзей поровну делят 235 рублей. Сколько рублей получит каждый? Ответь одним числом.")
    print(result)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 235 / 5 = 47. Проверяется строка ответа агента."""
    import re
    text = result
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)47(?!\d)", text) is not None
