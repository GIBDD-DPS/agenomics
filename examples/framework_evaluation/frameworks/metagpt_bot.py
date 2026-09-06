"""
Шаблон под MetaGPT (проверено по актуальной документации, 2026).

ВНИМАНИЕ: MetaGPT симулирует целую "software company" (product manager,
architect, engineer, QA) - один реальный прогон стоит ~$0.2-2 в LLM API
(по данным официальной документации). Если запускаете это в CI по
расписанию (framework_eval.yml, каждые 6 часов) - это будет ощутимо
дороже остальных 13 шаблонов. Возможно, стоит запускать MetaGPT реже.
"""

DOMAIN = "content"
AUTONOMY = "autonomous"  # генерирует и применяет код без промежуточного подтверждения


def run():
    from metagpt.software_company import generate_repo

    # investment - примерный бюджет в долларах на LLM-вызовы для этого прогона
    result = generate_repo(
        idea="Создай простую функцию сложения двух чисел",  # замените на вашу реальную задачу
        investment=1.0,
        n_round=3,
    )
    print(result)
    return result
