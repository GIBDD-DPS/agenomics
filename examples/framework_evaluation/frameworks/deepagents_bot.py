# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Deep Agents (LangChain): агент с планированием и файловой системой поверх LangGraph.
Требует переменную окружения GROQ_API_KEY (тот же ключ, что у остальных шаблонов).
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "deepagents"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # задача с проверяемым ответом
CI_TIER = "experimental"  # новый шаблон: experimental, пока не доказал стабильность в CI


def run():
    from deepagents import create_deep_agent

    agent = create_deep_agent(model="groq:openai/gpt-oss-20b", system_prompt="You are a helpful assistant.")
    result = agent.invoke({"messages": [{"role": "user", "content":
        "Велосипедист ехал 3 часа со скоростью 18 км/ч. Сколько километров он проехал? Ответь одним числом."}]})
    print(result["messages"][-1].content)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 3 * 18 = 54. Проверяется последнее сообщение агента."""
    import re
    messages = result.get("messages") if isinstance(result, dict) else None
    text = getattr(messages[-1], "content", None) if messages else None
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)54(?!\d)", text) is not None
