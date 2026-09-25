# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под LangGraph, переведён на Groq (бесплатный провайдер).
Требует пакет langchain-groq и переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "langgraph"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langchain_groq import ChatGroq

    model = ChatGroq(model="openai/gpt-oss-20b")

    def call_model(state: MessagesState):
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    graph_builder = StateGraph(MessagesState)
    graph_builder.add_node("llm", call_model)
    graph_builder.add_edge(START, "llm")
    graph_builder.add_edge("llm", END)

    graph = graph_builder.compile()

    result = graph.invoke({"messages": [{"role": "user", "content": "Товар стоил 250 рублей, на него дали скидку 20%. Сколько рублей он стоит со скидкой? Ответь одним числом."}]})
    print(result["messages"][-1].content)
    return result


def check(result) -> bool:
    """Задача с однозначным ответом: 250 * 0.8 = 200. Проверяется последнее сообщение графа (ответ модели)."""
    import re
    text = getattr(result["messages"][-1], "content", None) if isinstance(result, dict) and result.get("messages") else None
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)200(?!\d)", text) is not None
