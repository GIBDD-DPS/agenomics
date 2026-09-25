# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Griptape, переведён на Groq (бесплатный провайдер, через
OpenAI-совместимый эндпоинт api.groq.com). Требует GROQ_API_KEY.

Раньше этот шаблон уже успешно отрабатывал на OpenAI, это не смена
"проблемного" шаблона на рабочий, а перевод рабочего шаблона на
бесплатный провайдер, чтобы не тратить платные токены в CI.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "griptape"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    import os
    from griptape.drivers.prompt.openai import OpenAiChatPromptDriver
    from griptape.structures import Agent

    agent = Agent(
        prompt_driver=OpenAiChatPromptDriver(
            model="openai/gpt-oss-20b",
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        ),
    )

    agent.run("Прямоугольник имеет стороны 13 и 7. Чему равна его площадь? Ответь одним числом.")
    print("Answer:", agent.output)
    return agent.output


def check(result) -> bool:
    """Задача с однозначным ответом: 13 * 7 = 91. Проверяется значение артефакта ответа (agent.output.value)."""
    import re
    text = getattr(result, "value", result)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)91(?!\d)", text) is not None
