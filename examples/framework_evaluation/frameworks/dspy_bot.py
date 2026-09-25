# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под DSPy (Stanford), переведён на Groq (бесплатный провайдер).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "dspy"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v1"  # задача с ответом из инструмента, без изменений с v0.9.2
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    import dspy

    dspy.configure(lm=dspy.LM("groq/openai/gpt-oss-20b"))

    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"The weather in {city} is sunny and 22C"

    agent = dspy.ReAct(
        signature="question -> answer",
        tools=[get_weather],
        max_iters=5,
    )

    result = agent(question="Какая погода в Париже?")
    print(result.answer)
    return result


def check(result) -> bool:
    """Инструмент get_weather возвращает "sunny and 22C": правильный ответ
    обязан содержать 22. Проверяется итоговый ответ (result.answer), а не
    весь результат, где есть и вывод инструмента."""
    import re
    return re.search(r"(?<!\d)22(?!\d)", str(getattr(result, "answer", ""))) is not None
