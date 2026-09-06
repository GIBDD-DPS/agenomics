"""
Шаблон под AutoGPT. ВАЖНО: как и Rasa, AutoGPT в 2026 - это не простая
pip-библиотека, а полноценная self-hosted платформа (Docker Compose,
FastAPI backend), либо облачный сервис по листу ожидания. Обращаемся
через Agent Protocol (agentprotocol.ai) - открытый REST-стандарт,
которому соответствует классический AutoGPT Agent.

Перед запуском run() агент должен быть поднят и слушать порт (обычно
localhost:8000, зависит от вашей конфигурации).
"""

DOMAIN = "content"
AUTONOMY = "autonomous"

AGENT_PROTOCOL_URL = "http://localhost:8000/ap/v1/agent"


def run():
    import requests

    # Шаг 1: создать задачу
    task_resp = requests.post(
        f"{AGENT_PROTOCOL_URL}/tasks",
        json={"input": "Найди три главных риска в этом плане"},  # замените на вашу задачу
        timeout=30,
    )
    task_resp.raise_for_status()
    task = task_resp.json()

    # Шаг 2: выполнить шаг (может потребоваться несколько итераций
    # в зависимости от сложности задачи - здесь показан один шаг)
    step_resp = requests.post(
        f"{AGENT_PROTOCOL_URL}/tasks/{task['task_id']}/steps",
        json={"input": ""},
        timeout=60,
    )
    step_resp.raise_for_status()
    result = step_resp.json()
    print(result)
    return result
