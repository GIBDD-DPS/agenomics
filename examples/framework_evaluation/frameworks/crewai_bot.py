"""
Шаблон под CrewAI (проверено по актуальной документации, 2026).
Пример: исследователь + райтер. Замените роли/задачи на свои реальные.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from crewai import Agent, Task, Crew, Process

    researcher = Agent(
        role="Senior Research Analyst",
        goal="Найти последние разработки в области ИИ-агентов",
        backstory="Вы опытный аналитик индустрии.",
        llm="gpt-4o-mini",  # замените на вашу модель
    )

    writer = Agent(
        role="Tech Writer",
        goal="Превратить заметки исследования в краткую сводку",
        backstory="Вы пишете четко для инженеров.",
        llm="gpt-4o-mini",
    )

    research_task = Task(
        description="Обзор трех последних разработок в области ИИ-агентов.",
        expected_output="Список из пунктов с находками.",
        agent=researcher,
    )

    write_task = Task(
        description="Составьте краткую сводку на основе исследования.",
        expected_output="Markdown-сводка.",
        agent=writer,
        context=[research_task],
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.sequential,
    )

    result = crew.kickoff()
    print(result.raw)
    return result
