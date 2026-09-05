"""
Шаблон под AG2 (бывший AutoGen, пакет теперь называется ag2/pyautogen).
ВНИМАНИЕ: если вы используете именно оригинальный Microsoft AutoGen
(pyautogen до форка 2024 года) - синтаксис другой, дайте знать отдельно.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from autogen import ConversableAgent, LLMConfig

    llm_config = LLMConfig({"api_type": "openai", "model": "gpt-4o-mini"})

    agent = ConversableAgent(
        name="assistant",
        system_message="You are a helpful assistant",
        llm_config=llm_config,
    )

    response = agent.run(message="Объясни, что такое agentic AI", max_turns=1)
    response.process()
    return response
