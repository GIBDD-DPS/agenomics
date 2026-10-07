# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Swarms (Agent) на Groq через litellm.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "swarms"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from loguru import logger
    from swarms import Agent

    # адрес Groq через litellm: GROQ_API_BASE. output_type="final": только
    # итоговый ответ, а не вся история диалога вместе с текстом задачи (в
    # stress_security там лежит канарейка, и её «раскрытие» было бы ложным).
    agent = Agent(
        agent_name="Assistant", system_prompt=ctx.system, model_name=ctx.litellm_model,
        max_loops=1, output_type="final",
    )
    # [v0.9.5] Swarms не бросает исключение при ошибке провайдера (нет сети,
    # 401, 429): после retry_attempts пишет ошибку в лог loguru и
    # возвращает пустую строку. Без перехвата сбой прогона записывался бы
    # как неверный ответ агента (task_failure), а не как ошибка выполнения,
    # и причина (например, rate limit) терялась бы.
    errors = []
    sink = logger.add(lambda message: errors.append(message.record["message"]), level="ERROR")
    try:
        result = agent.run(ctx.prompt)
    finally:
        logger.remove(sink)
    print(result)
    if not str(result or "").strip() and errors:
        raise RuntimeError(errors[0][:500])
    # При ошибке модели output_type="final" возвращает последнее сообщение
    # истории, то есть сам запрос пользователя. Это не ответ агента.
    if str(result or "").strip() == ctx.prompt.strip():
        raise RuntimeError(errors[0][:500] if errors else "swarms вернул запрос вместо ответа модели")
    return result


def answer(result) -> str:
    """Итоговый ответ (строка с output_type="final")."""
    if result is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(result)
