"""
Шаблон под Langroid, проверено по актуальной документации, 2026.

ВНИМАНИЕ (безопасность): в 2026 году зафиксирована уязвимость
PYSEC-2026-2579 (CVSS 8.1 High) - handle_message() может выполнить
произвольный tool-вызов из пользовательского сообщения без проверки
отправителя, даже если tool зарегистрирован с use=False. Если ваш
Langroid-агент принимает ввод от недоверенных пользователей и
использует enable_message(..., handle=True) - проверьте версию
пакета и патч перед продакшен-использованием.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    import langroid as lr

    config = lr.ChatAgentConfig(
        llm=lr.language_models.OpenAIGPTConfig(
            chat_model=lr.language_models.OpenAIChatModel.GPT4o,  # замените на вашу модель
        ),
        vecdb=None,
    )
    agent = lr.ChatAgent(config)
    task = lr.Task(agent, name="Bot", interactive=False)

    result = task.run("Что такое Langroid?", turns=1)  # замените на вашу реальную задачу
    print(result.content)
    return result
