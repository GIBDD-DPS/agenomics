# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под LangGraph (граф из одного узла с моделью) на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "langgraph"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from langchain_groq import ChatGroq
    from langgraph.graph import END, START, MessagesState, StateGraph

    # ChatGroq берёт адрес из GROQ_BASE_URL (корень, без /openai/v1)
    model = ChatGroq(model=ctx.model, api_key=ctx.api_key)

    def call_model(state: MessagesState):
        return {"messages": [model.invoke(state["messages"])]}

    graph_builder = StateGraph(MessagesState)
    graph_builder.add_node("llm", call_model)
    graph_builder.add_edge(START, "llm")
    graph_builder.add_edge("llm", END)
    graph = graph_builder.compile()

    result = graph.invoke({"messages": [{"role": "system", "content": ctx.system},
                                        {"role": "user", "content": ctx.prompt}]})
    print(result["messages"][-1].content)
    return result


def answer(result) -> str:
    """Последнее сообщение графа (ответ модели)."""
    messages = result.get("messages") if isinstance(result, dict) else None
    text = getattr(messages[-1], "content", None) if messages else None
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
