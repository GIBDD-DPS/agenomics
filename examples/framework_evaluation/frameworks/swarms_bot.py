# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
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
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from swarms import Agent

    agent = Agent(
        agent_name="Assistant",
        system_prompt="You are a helpful assistant.",
        model_name="groq/openai/gpt-oss-20b",  # тот же формат litellm-строки, что и в CrewAI/DSPy
        max_loops=1,
    )

    # [v0.9.5] Swarms не бросает исключение при ошибке провайдера (нет сети,
    # 401, 429): после retry_attempts пишет ошибку в лог loguru и
    # возвращает пустую строку. Без перехвата сбой прогона записывался бы
    # как неверный ответ агента (task_failure), а не как ошибка выполнения,
    # и причина (например, rate limit) терялась бы.
    from loguru import logger
    errors = []
    sink = logger.add(lambda message: errors.append(message.record["message"]), level="ERROR")
    try:
        result = agent.run("Каждую неделю откладывают 150 рублей. Сколько рублей отложат за 12 недель? Ответь одним числом.")
    finally:
        logger.remove(sink)
    print(result)
    if not str(result or "").strip() and errors:
        raise RuntimeError(errors[0][:500])
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 150 * 12 = 1800. Проверяется строка, которую вернул agent.run(). В зависимости от output_type в ней может быть и
    история диалога с текстом задачи, поэтому ответ выбран так, что в условии его нет."""
    import re
    text = result
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)1800(?!\d)", text) is not None
