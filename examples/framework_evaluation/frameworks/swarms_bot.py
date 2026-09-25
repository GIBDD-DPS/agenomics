# Agenomics 0.9.3 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Swarms (kyegomez/swarms), переведён на Groq (бесплатный
провайдер, без карты). Требует переменную окружения GROQ_API_KEY.

Не путать с устаревшим OpenAI Swarm (deprecated с марта 2025, заменён
на OpenAI Agents SDK) - это отдельный, самостоятельный, активно
развивающийся проект с собственной архитектурой.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "swarms"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from swarms import Agent

    agent = Agent(
        agent_name="Assistant",
        system_prompt="You are a helpful assistant.",
        model_name="groq/openai/gpt-oss-20b",  # тот же формат litellm-строки, что и в CrewAI/DSPy
        max_loops=1,
    )

    result = agent.run("Что такое Swarms в двух предложениях?")  # замените на вашу реальную задачу
    print(result)
    return result
