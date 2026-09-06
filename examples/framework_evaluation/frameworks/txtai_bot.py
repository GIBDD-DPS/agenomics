"""
Шаблон под txtai (NeuML), проверено по актуальной документации, 2026.

Заменяет изначально предложенную Eliza (ai16z) - та написана на
TypeScript/Node.js, а не Python, и не вписалась бы в наш пайплайн
def run(): без городения subprocess-обёртки вокруг Node.js.

Честная оговорка: txtai.Agent построен поверх smolagents (тот же
движок, что и у уже добавленного smolagents_bot.py), но это отдельный,
активно поддерживаемый пакет NeuML с собственным фокусом на embeddings
и RAG, а не просто дубликат.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from txtai import Agent

    def today() -> str:
        """Gets the current date and time."""
        from datetime import datetime
        return datetime.today().isoformat()

    agent = Agent(
        model="gpt-4o-mini",  # замените на вашу модель
        tools=[today, "websearch"],  # замените на ваши реальные инструменты/embeddings-базы
        max_iterations=5,
    )

    result = agent("Что такое txtai в двух предложениях?")  # замените на вашу реальную задачу
    print(result)
    return result
