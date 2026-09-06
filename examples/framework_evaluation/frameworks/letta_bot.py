"""
Шаблон под Letta (бывший MemGPT), проверено по документации letta-client, 2026.

ВАЖНО: как и Rasa, Letta - клиент-серверная архитектура. Нужен либо
Letta Cloud (переменная окружения LETTA_API_KEY), либо локально
запущенный Letta-сервер (Docker, base_url="http://localhost:8283").
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import os
    from letta_client import Letta

    client = Letta(api_key=os.getenv("LETTA_API_KEY"))  # или base_url="http://localhost:8283" для self-hosted

    agent_state = client.agents.create(
        model="openai/gpt-4o-mini",  # замените на вашу модель
        embedding="openai/text-embedding-3-small",
        memory_blocks=[
            {"label": "persona", "value": "You are a helpful assistant."},
        ],
    )

    response = client.agents.messages.create(
        agent_id=agent_state.id,
        input="Что такое Letta в двух предложениях?",  # замените на вашу реальную задачу
    )

    for message in response.messages:
        if message.message_type == "assistant_message":
            print(message.content)
    return response
