"""
Шаблон под CrewAI, переведён на Groq (бесплатный провайдер, через litellm).
Требует переменную окружения GROQ_API_KEY.

ИЗВЕСТНАЯ ПРОБЛЕМА (не исправима на нашей стороне): в CrewAI открыт баг
github.com/crewAIInc/crewAI/issues/5886 - cache_breakpoint добавляется
во все сообщения независимо от провайдера, но снимается только для
Anthropic. Groq и другие OpenAI-совместимые провайдеры отклоняют
запрос с этим полем. Если это всё ещё воспроизводится - смотрите
статус issue, возможно, обновление CrewAI уже решило это к моменту
вашего запуска.
"""

DOMAIN = "content"
AUTONOMY = "advisory"


def run():
    from crewai import Agent, Task, Crew, Process

    researcher = Agent(
        role="Senior Research Analyst",
        goal="Найти последние разработки в области ИИ-агентов",
        backstory="Вы опытный аналитик индустрии.",
        llm="groq/openai/gpt-oss-20b",
    )

    writer = Agent(
        role="Tech Writer",
        goal="Превратить заметки исследования в краткую сводку",
        backstory="Вы пишете четко для инженеров.",
        llm="groq/openai/gpt-oss-20b",
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
