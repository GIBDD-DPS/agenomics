# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под CAMEL-AI, переведён на Groq (бесплатный провайдер).
Требует переменную окружения GROQ_API_KEY.

ВАЖНО: список enum ModelType.GROQ_* в CAMEL сам устарел (там только
уже снятые с производства модели вроде llama-3.3-70b). CAMEL поддерживает
произвольную строку в model_type в обход enum. Используем этот путь.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "camel-ai"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте


def run():
    from camel.agents import ChatAgent
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType
    from camel.configs import GroqConfig

    model = ModelFactory.create(
        model_platform=ModelPlatformType.GROQ,
        model_type="openai/gpt-oss-20b",  # строка, не устаревший enum
        model_config_dict=GroqConfig(temperature=0.2).as_dict(),
    )

    agent = ChatAgent(model=model)

    response = agent.step("В книге 240 страниц, прочитано 3/8 книги. Сколько страниц осталось прочитать? Ответь одним числом.")
    print(response.msgs[0].content)
    return response


def check(result) -> bool:
    """Задача с однозначным ответом: 240 * 5/8 = 150. Проверяется первое сообщение ответа (msgs[0].content)."""
    import re
    msgs = getattr(result, "msgs", None) or []
    text = getattr(msgs[0], "content", None) if msgs else None
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)150(?!\d)", text) is not None
