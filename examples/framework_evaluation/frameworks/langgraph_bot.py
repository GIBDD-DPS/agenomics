"""
Шаблон под LangGraph, переведён на Groq (бесплатный провайдер).
Требует пакет langchain-groq и переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langchain_groq import ChatGroq

    model = ChatGroq(model="llama-3.3-70b-versatile")

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
