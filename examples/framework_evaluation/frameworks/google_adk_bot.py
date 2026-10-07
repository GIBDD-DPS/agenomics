# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Google ADK на Groq через LiteLLM (без Gemini и GOOGLE_API_KEY).
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "google-adk"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    import asyncio
    from google.adk.agents import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = Agent(
        name="assistant",
        model=LiteLlm(model=ctx.litellm_model, api_base=ctx.base_url, api_key=ctx.api_key),
        instruction=ctx.system,
    )
    runner = InMemoryRunner(agent=agent, app_name="agenomics_eval")

    async def _run():
        content = types.Content(role="user", parts=[types.Part.from_text(text=ctx.prompt)])
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


def answer(result) -> str:
    """Последний текстовый фрагмент среди событий агента."""
    texts = [part.text for event in (result or []) if getattr(event, "content", None) and event.content.parts
             for part in event.content.parts if getattr(part, "text", None)]
    if not texts:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(texts[-1])
