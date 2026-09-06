"""
Шаблон под Rasa. ВАЖНО: в отличие от остальных фреймворков в этой папке,
Rasa НЕ вызывается как обычная Python-библиотека - классический Rasa
Open Source сейчас в maintenance mode, а актуальный CALM/Rasa Pro
требует отдельно запущенного сервера (rasa run --enable-api) и
общается через REST API, а не прямой импорт класса агента.

Перед запуском run() у вас должен быть поднят Rasa-сервер:
    rasa run --enable-api

Если вы используете CALM/Rasa Pro (YAML-flows) - endpoint тот же,
но потребуется лицензия rasa-pro. Замените RASA_URL на реальный адрес
вашего сервера, если он не локальный.
"""

DOMAIN = "content"
AUTONOMY = "advisory"

RASA_URL = "http://localhost:5005/webhooks/rest/webhook"


def run():
    import requests

    response = requests.post(
        RASA_URL,
        json={"sender": "agenomics-eval", "message": "Привет, что ты умеешь?"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    print(data)
    return data
