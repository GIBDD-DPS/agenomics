# Agenomics 0.9.4 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
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
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "autogen"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


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

    response = agent.run(message="Поезд ехал 2 часа со скоростью 65 км/ч, затем 1 час со скоростью 40 км/ч. Сколько километров он проехал? Ответь одним числом.", max_turns=1)
    response.process()
    return response


def check(result) -> bool:
    """Задача с однозначным ответом: 2 * 65 + 40 = 170. Проверяется итог диалога (summary), иначе последнее сообщение."""
    import re
    text = getattr(result, "summary", None)
    if not text:
        messages = list(getattr(result, "messages", None) or [])
        text = messages[-1].get("content") if messages and isinstance(messages[-1], dict) else None
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)170(?!\d)", text) is not None
