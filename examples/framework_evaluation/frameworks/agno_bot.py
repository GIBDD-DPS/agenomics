# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Agno (бывший Phidata), переведён на Groq (бесплатный провайдер).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "agno"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from agno.agent import Agent
    from agno.models.groq import Groq

    agent = Agent(
        model=Groq(id="openai/gpt-oss-20b"),
        description="You are a helpful assistant.",
        markdown=True,
    )

    response = agent.run("В коробке 14 карандашей. Из неё взяли 5, потом положили 9. Сколько карандашей в коробке? Ответь одним числом.")
    print(response.content)
    # [v0.9.5] Agno не бросает исключение при ошибке провайдера (нет сети,
    # 401, 429): RunOutput получает status=ERROR, а текст ошибки попадает в
    # content. Без этой проверки сбой прогона записывался бы как неверный
    # ответ агента (task_failure), а не как ошибка выполнения.
    if getattr(getattr(response, "status", None), "value", None) == "ERROR":
        raise RuntimeError(f"agno RunStatus.ERROR: {response.content}")
    return response


def check(result) -> bool:
    """Задача с однозначным ответом: 14 - 5 + 9 = 18. Проверяется текст ответа (RunOutput.content)."""
    import re
    text = getattr(result, "content", None)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)18(?!\d)", text) is not None
