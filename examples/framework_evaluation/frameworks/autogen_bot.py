"""
Шаблон под AG2 Classic (ConversableAgent/LLMConfig), переведён на Groq
(бесплатный провайдер). Требует переменную окружения GROQ_API_KEY.

ВАЖНО: с AG2 v1.0 пакет `ag2` больше не даёт импорт `autogen` (классический
API переехал в отдельный пакет). Устанавливайте через `pip install autogen`
(или `pip install pyautogen`/`pip install ag2-classic`), не `pip install ag2` -
именно так теперь настроено в framework_eval.yml. Код ниже не меняется.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import os
    from autogen import ConversableAgent, LLMConfig

    llm_config = LLMConfig({
        "api_type": "groq",
        "model": "openai/gpt-oss-20b",
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
