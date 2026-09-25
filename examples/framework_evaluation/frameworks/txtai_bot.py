# Agenomics 0.9.3 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под txtai (NeuML), переведён на Groq (бесплатный провайдер, через
litellm-стиль строки модели, унаследованный от smolagents под капотом).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "txtai"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте


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

    result = agent("Что такое txtai в двух предложениях?")
    print(result)
    return result
