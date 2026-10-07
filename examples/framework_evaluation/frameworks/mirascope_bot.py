# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
Шаблон под Mirascope v2 (llm.call), OpenAI-совместимый провайдер на Groq.
Модель, задачу и системный промпт задаёт раннер (conditions.RunContext):
шаблон только строит агента своего фреймворка и вызывает его. Требует
GROQ_API_KEY.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
FRAMEWORK_PACKAGE = "mirascope"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте

def run(ctx):
    from mirascope import llm

    # Mirascope требует id вида "провайдер/модель" и не всегда передаёт его
    # в API как есть. Модель с "/" (openai/gpt-oss-20b, qwen/qwen3-32b) идёт
    # через провайдер together: он отправляет id целиком. Модель без "/"
    # (llama-3.3-70b-versatile) через openai: он отрезает "openai/", а
    # ":completions" выбирает Chat Completions вместо Responses API.
    if "/" in ctx.model:
        llm.register_provider("together", scope=ctx.model, api_key=ctx.api_key, base_url=ctx.base_url)
        model_id = ctx.model
    else:
        llm.register_provider("openai", scope=f"openai/{ctx.model}", api_key=ctx.api_key, base_url=ctx.base_url)
        model_id = f"openai/{ctx.model}:completions"

    @llm.call(model_id)
    def solve():
        return [llm.messages.system(ctx.system), llm.messages.user(ctx.prompt)]

    response = solve()
    print(response.text())
    return response


def answer(result) -> str:
    """Текст ответа (response.text())."""
    text = result.text() if callable(getattr(result, "text", None)) else None
    if text is None:
        raise ValueError(f"неожиданная форма результата: {type(result).__name__}")  # исход неизвестен, а не провал агента
    return str(text)
