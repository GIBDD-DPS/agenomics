# Agenomics 0.9.6 | Author: Dm.Andreyanov | Brand: Prizolov Lab | © 2026
"""
judge.py — второй донор task_failure: LLM-судья на другой модели Groq.

Судья видит только условие задачи и итоговый ответ агента. Trust Score,
имя фреймворка, эталонный ответ и результат детерминированной проверки
он не видит: задачу он решает сам. Поэтому его ошибка другого рода, чем
у task_checker, и это отдельная группа независимости (llm_judge).

Модель судьи всегда отличается от модели агента в этом прогоне. Если
судья не ответил или ответ не разобран, исхода от него нет: это
«неизвестно», а не провал задачи.

Только stdlib.

Проект: Prizolov Lab
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable, Optional, Tuple

from conditions import DEFAULT_BASE_URL, judge_model_for

JUDGE_PROMPT = (
    "Ты проверяешь ответ ассистента на задачу. Реши задачу сам, затем сравни итоговое число в ответе "
    "ассистента со своим. Ответь одним словом: YES, если итоговый ответ ассистента верен, иначе NO.\n\n"
    "Задача:\n{task}\n\nОтвет ассистента:\n{answer}"
)
_VERDICT = re.compile(r"\b(YES|NO)\b")
USER_AGENT = "agenomics-framework-eval/1 (+https://github.com/GIBDD-DPS/agenomics)"


def parse_verdict(text: str) -> Optional[bool]:
    """Последнее YES или NO в ответе судьи (рассуждение может идти до него);
    None, если ни того ни другого нет."""
    found = _VERDICT.findall(str(text or "").upper())
    return None if not found else found[-1] == "YES"


def ask_groq(model: str, prompt: str, timeout: float = 60.0) -> str:
    base = os.environ.get("AGENOMICS_JUDGE_BASE") or os.environ.get("GROQ_API_BASE") or DEFAULT_BASE_URL
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 1024,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    request = urllib.request.Request(
        base.rstrip("/") + "/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}",
                 # Groq за Cloudflare: стандартный User-Agent "Python-urllib" получает 403
                 "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"] or ""


def judge_answer(task_prompt: str, answer_text: str, agent_model: str,
                 ask: Callable[[str, str], str] = ask_groq) -> Tuple[Optional[str], Optional[bool], Optional[str]]:
    """(модель судьи, верен ли ответ или None, ошибка или None)."""
    model = judge_model_for(agent_model)
    if model is None:
        return None, None, "нет модели судьи, отличной от модели агента"
    try:
        verdict = parse_verdict(ask(model, JUDGE_PROMPT.format(task=task_prompt, answer=answer_text)))
    except urllib.error.HTTPError as exc:
        return model, None, f"HTTPError {exc.code}: {exc.read()[:120]!r}"[:200]
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError) as exc:
        return model, None, f"{type(exc).__name__}: {exc}"[:200]
    return model, verdict, None if verdict is not None else "ответ судьи не разобран"
