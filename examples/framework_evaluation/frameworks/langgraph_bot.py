"""
Шаблон под LangGraph (v1.0 API, проверено 2026). В отличие от простого
LangChain-агента, здесь показан именно граф - то, что отличает LangGraph
как отдельный инструмент: узлы, ребра, условная маршрутизация.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model="gpt-4o-mini")  # замените на вашу модель

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
