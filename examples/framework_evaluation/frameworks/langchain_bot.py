# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под LangChain, переведён на Groq (бесплатный провайдер, без карты).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "langchain"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from langchain.agents import create_agent

    def get_weather(city: str) -> str:
        """Get weather for a given city."""
        return f"It's always sunny in {city}!"

    agent = create_agent(
        model="groq:openai/gpt-oss-20b",
        tools=[get_weather],
        system_prompt="You are a helpful assistant",
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Какая погода в Сан-Франциско?"}]}
    )
    print(result["messages"][-1].content)
    return result


def check(result) -> bool:
    """Инструмент get_weather возвращает "It's always sunny": правильный
    ответ должен сказать, что солнечно. Проверяется только последнее
    сообщение (ответ модели): в предыдущих лежит вывод самого инструмента,
    и проверка по всему результату прошла бы при любом ответе."""
    text = str(getattr(result["messages"][-1], "content", "")).lower()
    return "sunny" in text or "солн" in text
