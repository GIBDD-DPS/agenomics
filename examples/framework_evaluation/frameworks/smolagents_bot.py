# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под smolagents (Hugging Face): CodeAgent, модель Groq через LiteLLM.
Требует переменную окружения GROQ_API_KEY.

До v0.9.5 шаблон ходил в Hugging Face Inference API и требовал HF_TOKEN,
которого в CI нет: все прогоны падали с provider_routing_error.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "smolagents"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v1"  # задача не менялась с v0.9.2: сумма 1..10
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте


def run():
    from smolagents import CodeAgent, LiteLLMModel

    # [v0.9.5] Groq вместо Hugging Face Inference: в CI нет HF_TOKEN, и все
    # прогоны на HF уходили в provider_routing_error, не давая данных об
    # агенте. Смена модели видна в EvidenceStore через model_version.
    model = LiteLLMModel(model_id="groq/openai/gpt-oss-20b")
    agent = CodeAgent(tools=[], model=model)

    result = agent.run("Посчитай сумму чисел от 1 до 10")
    print(result)
    return result


def check(result) -> bool:
    """Задача детерминированная: сумма чисел от 1 до 10 равна 55. Пишется
    в EvidenceStore донором task_checker как исход task_failure."""
    import re
    return re.search(r"(?<!\d)55(?!\d)", str(result)) is not None
