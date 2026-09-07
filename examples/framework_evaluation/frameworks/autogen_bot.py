"""
Шаблон под AG2 (бывший AutoGen), переведён на Groq (бесплатный провайдер).
Требует переменную окружения GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import os
    from autogen import ConversableAgent, LLMConfig

    llm_config = LLMConfig({
        "api_type": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_key": os.environ.get("GROQ_API_KEY"),
    })

    agent = ConversableAgent(
        name="assistant",
        system_message="You are a helpful assistant",
        llm_config=llm_config,
    )

    response = agent.run(message="Объясни, что такое agentic AI", max_turns=1)
    response.process()
    return response
