"""
Шаблон под OpenAI Agents SDK, переведён на Groq (бесплатный провайдер,
через OpenAI-совместимый эндпоинт, тот же приём, что для Haystack/
Griptape/Semantic Kernel). Официально подтверждено документацией SDK:
OpenAIChatCompletionsModel принимает готовый AsyncOpenAI-клиент с любым
base_url. Требует GROQ_API_KEY.

Был в исходном списке из 14 фреймворков, убран при сокращении до 15 как
"слишком привязанный к OpenAI". Оказалось, это не так - официальный
путь для сторонних провайдеров есть, просто не был известен на тот
момент.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import os
    from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, set_tracing_disabled

    set_tracing_disabled(disabled=True)  # трейсинг по умолчанию шлёт данные в OpenAI, не нужно для Groq

    groq_client = AsyncOpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    model = OpenAIChatCompletionsModel(model="openai/gpt-oss-20b", openai_client=groq_client)

    agent = Agent(name="Assistant", instructions="You are a helpful assistant.", model=model)

    result = Runner.run_sync(agent, "Что такое OpenAI Agents SDK?")  # замените на вашу реальную задачу
    print(result.final_output)
    return result
