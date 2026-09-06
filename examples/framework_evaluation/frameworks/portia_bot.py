"""
Шаблон под Portia AI, проверено по актуальной документации, 2026.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from portia import Portia, example_tool_registry

    portia = Portia(tools=example_tool_registry)  # использует OpenAI по умолчанию

    plan_run = portia.run("Что такое Portia AI?")  # замените на вашу реальную задачу
    print(plan_run.model_dump_json(indent=2))
    return plan_run
