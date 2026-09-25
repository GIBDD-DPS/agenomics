# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Google ADK (Agent Development Kit), модель Groq через LiteLlm.
Требует переменную окружения GROQ_API_KEY.

До v0.9.5 шаблон вызывал Gemini и требовал GOOGLE_API_KEY, которого в CI
нет: все прогоны падали с auth_error.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "google-adk"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте


def run():
    import asyncio
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    # [v0.9.5] Groq через LiteLLM вместо Gemini: в CI нет GOOGLE_API_KEY, и
    # все прогоны уходили в auth_error, не давая данных об агенте.
    agent = Agent(
        name="assistant",
        model=LiteLlm(model="groq/openai/gpt-oss-20b"),
        instruction="You are a helpful assistant.",
    )

    runner = InMemoryRunner(agent=agent, app_name="agenomics_eval")

    async def _run():
        content = types.Content(role="user", parts=[types.Part.from_text(text="Чему равна сумма всех целых чисел от 1 до 20? Ответь одним числом.")])
        session = await runner.session_service.create_session(app_name="agenomics_eval", user_id="eval")
        events = []
        async for event in runner.run_async(user_id="eval", session_id=session.id, new_message=content):
            events.append(event)
        return events

    events = asyncio.run(_run())
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(part.text)
    return events


def check(result) -> bool:
    """Задача с однозначным ответом: 1 + 2 + ... + 20 = 210. Проверяется последний текстовый фрагмент в событиях агента."""
    import re
    texts = [part.text for event in (result or []) if getattr(event, "content", None) and event.content.parts
             for part in event.content.parts if getattr(part, "text", None)]
    text = texts[-1] if texts else None
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)210(?!\d)", text) is not None
