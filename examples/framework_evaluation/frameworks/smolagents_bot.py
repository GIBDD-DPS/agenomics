"""
Шаблон под smolagents (Hugging Face).

Обновление: анонимный доступ к Hugging Face Inference API без токена
перестал работать в CI (реальная находка из логов: "You must provide
an api_key to work with auto API or log in with hf auth login").
Нужен бесплатный токен с huggingface.co/settings/tokens, положенный в
переменную окружения HF_TOKEN.
"""

DOMAIN = "content"
AUTONOMY = "advisory"
MODEL_VERSION = "huggingface/Qwen/Qwen3-Next-80B-A3B-Thinking"  # провайдер/модель, записывается в EvidenceStore.model_version
FRAMEWORK_PACKAGE = "smolagents"  # имя дистрибутива для importlib.metadata.version()
CI_TIER = "experimental"  # required: падение валит CI; experimental: только в отчёте


def run():
    import os
    from smolagents import CodeAgent, InferenceClientModel

    # model_id зафиксирован явно: без него smolagents берёт свой дефолт,
    # который менялся между версиями библиотеки, и MODEL_VERSION
    # перестал бы соответствовать реально вызванной модели. Значение
    # совпадает с дефолтом smolagents 1.26.0, поведение не меняется.
    model = InferenceClientModel(
        model_id="Qwen/Qwen3-Next-80B-A3B-Thinking", token=os.environ.get("HF_TOKEN"),
    )
    agent = CodeAgent(tools=[], model=model)

    result = agent.run("Посчитай сумму чисел от 1 до 10")
    print(result)
    return result
