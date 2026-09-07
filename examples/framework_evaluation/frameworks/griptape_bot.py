"""
Шаблон под Griptape, переведён на Groq (бесплатный провайдер, через
OpenAI-совместимый эндпоинт api.groq.com). Требует GROQ_API_KEY.

Раньше этот шаблон уже успешно отрабатывал на OpenAI, это не смена
"проблемного" шаблона на рабочий, а перевод рабочего шаблона на
бесплатный провайдер, чтобы не тратить платные токены в CI.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import os
    from griptape.drivers.prompt.openai import OpenAiChatPromptDriver
    from griptape.structures import Agent

    agent = Agent(
        prompt_driver=OpenAiChatPromptDriver(
            model="openai/gpt-oss-20b",
            api_key=os.environ.get("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        ),
    )

    agent.run("Что такое Griptape в двух предложениях?")
    print("Answer:", agent.output)
    return agent.output
