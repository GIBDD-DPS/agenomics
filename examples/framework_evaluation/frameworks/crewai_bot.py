# Agenomics 0.9.5 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
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
MODEL_VERSION = "groq/openai/gpt-oss-20b"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "crewai"  # имя дистрибутива для importlib.metadata.version()
PROMPT_VERSION = "task-v2"  # с 0.9.4 задача с проверяемым ответом вместо открытого вопроса
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте
DISABLED = "known_upstream_bug в каждом прогоне CI (внешний баг CrewAI, конфликт pydantic<2.13), 0% надёжности"  # v0.9.5: прогоны не запускаются, история сохраняется


def run():
    from crewai import Agent, Task, Crew, Process

    researcher = Agent(
        role="Senior Research Analyst",
        goal="Точно решать арифметические задачи",
        backstory="Вы опытный аналитик индустрии.",
        llm="groq/openai/gpt-oss-20b",
    )

    writer = Agent(
        role="Tech Writer",
        goal="Сформулировать итоговый ответ по решению аналитика",
        backstory="Вы пишете четко для инженеров.",
        llm="groq/openai/gpt-oss-20b",
    )

    research_task = Task(
        description="Магазин продал 48 чашек в понедельник и вдвое больше во вторник. Сколько чашек продано за два дня?",
        expected_output="Решение по шагам с итоговым числом.",
        agent=researcher,
    )

    write_task = Task(
        description="По решению аналитика дайте итоговый ответ на задачу.",
        expected_output="Одно число.",
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


def check(result) -> bool:
    """Задача с однозначным ответом: 48 + 2 * 48 = 144. Проверяется итог последней задачи экипажа (result.raw)."""
    import re
    text = getattr(result, "raw", None)
    if text is None:  # форма результата не та, что ожидалась: исход неизвестен, а не провал агента
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")
    text = re.sub(r"(?<=\d)[\s\u00a0\u202f,.](?=\d{3}(?!\d))", "", str(text or ""))  # 1 800, 1,800 -> 1800
    return re.search(r"(?<!\d)144(?!\d)", text) is not None
