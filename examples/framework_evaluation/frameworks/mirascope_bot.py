# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Mirascope (v2, `mirascope.llm`), модель Groq.
Требует переменную окружения GROQ_API_KEY (тот же ключ, что у остальных шаблонов).

Groq подключается через провайдер together с base_url Groq: он передаёт
идентификатор модели как есть. Провайдер openai отрезал бы всё после
первого "/", и в Groq ушло бы "openai" вместо "openai/gpt-oss-20b".
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "mirascope"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # задача с проверяемым ответом
CI_TIER = "experimental"  # новый шаблон: experimental, пока не доказал стабильность в CI


def run():
    import os
    from mirascope import llm

    llm.register_provider(
        "together", scope="openai/gpt-oss-",
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url=os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1"),
    )

    @llm.call("openai/gpt-oss-20b")
    def solve():
        return "Сколько минут в 2 часах и 15 минутах? Ответь одним числом."

    response = solve()
    print(response.text())
    return response


def check(result) -> bool:
    """Задача с однозначным ответом: 2 * 60 + 15 = 135. Проверяется текст ответа (Response.text())."""
    import re
    text = result.text() if callable(getattr(result, "text", None)) else None
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s  ,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)135(?!\d)", text) is not None
