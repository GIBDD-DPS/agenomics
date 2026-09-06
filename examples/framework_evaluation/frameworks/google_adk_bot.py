"""
Шаблон под Google ADK (Agent Development Kit), проверено по актуальной
документации, 2026.

Заменяет изначально предложенный BabyAGI - тот фактически неактивен
(ни одного смёрженного PR с мая 2024), официально описывается автором
как экспериментальный, "не для продакшена", и не является нормально
версионируемым pip-пакетом. Google ADK - реальный, активно
поддерживаемый SDK, закрывает пробел: у нас были Microsoft/AWS/OpenAI/
Hugging Face, но не было ничего от Google.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import asyncio
    from google.adk.agents import Agent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = Agent(
        name="assistant",
        model="gemini-2.5-flash",  # замените на вашу модель, нужен GOOGLE_API_KEY
        instruction="You are a helpful assistant.",
    )

    runner = InMemoryRunner(agent=agent, app_name="agenomics_eval")

    async def _run():
        content = types.Content(role="user", parts=[types.Part.from_text(text="Что такое Google ADK?")])
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
