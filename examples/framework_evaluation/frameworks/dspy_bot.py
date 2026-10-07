# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под DSPy (ChainOfThought) на Groq через litellm.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "dspy"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "required"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    import dspy

    # cache=False: одинаковое условие у агентов одного запуска не должно
    # отвечать из кэша DSPy вместо модели.
    dspy.configure(lm=dspy.LM(ctx.litellm_model, api_base=ctx.base_url, api_key=ctx.api_key, cache=False))
    program = dspy.ChainOfThought("question -> answer")
    result = program(question=f"{ctx.system}\n\n{ctx.prompt}")
    print(result.answer)
    return result


def answer(result) -> str:
    """Итоговый ответ (result.answer), без рассуждения."""
    text = getattr(result, "answer", None)
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
