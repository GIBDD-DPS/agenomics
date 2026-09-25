# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Strands Agents (AWS), модель Groq через LiteLLM.
Требует переменную окружения GROQ_API_KEY (тот же ключ, что у остальных шаблонов).
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "strands-agents"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # задача с проверяемым ответом
CI_TIER = "experimental"  # новый шаблон: experimental, пока не доказал стабильность в CI


def run():
    from strands import Agent
    from strands.models.litellm import LiteLLMModel

    agent = Agent(
        model=LiteLLMModel(model_id="groq/openai/gpt-oss-20b"),
        system_prompt="You are a helpful assistant.",
        callback_handler=None,  # без потокового вывода в консоль
    )
    result = agent("В саду 6 рядов по 15 деревьев, 4 дерева засохли. Сколько деревьев осталось? Ответь одним числом.")
    print(result)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 6 * 15 - 4 = 86. Проверяется текст итогового сообщения агента (AgentResult.message)."""
    import re
    message = getattr(result, "message", None)
    text = "".join(block.get("text", "") for block in message.get("content", [])) if isinstance(message, dict) else None
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)86(?!\d)", text) is not None
