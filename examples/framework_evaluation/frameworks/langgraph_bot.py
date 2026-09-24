"""
Шаблон под LangGraph, переведён на Groq (бесплатный провайдер).
Требует пакет langchain-groq и переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "langgraph"  # имя дистрибутива для importlib.metadata.version()
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

    result = graph.invoke({"messages": [{"role": "user", "content": "Что такое LangGraph?"}]})
    print(result["messages"][-1].content)
    return result
