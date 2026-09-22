"""RouterAI LLM client (OpenAI-compatible).

Docs: https://routerai.ru/docs/guides
Base URL: https://routerai.ru/api/v1  (endpoint /chat/completions)

Настройка через переменные окружения:
  ROUTERAI_API_KEY   — ключ из https://routerai.ru/settings/keys
  ROUTERAI_BASE_URL  — по умолчанию https://routerai.ru/api/v1
  SITEGEN_MODEL      — модель генерации сайта (по умолчанию DeepSeek V4 Pro —
                       дешёвая и качественная: ~97/293 ₽ за 1М токенов)
  SITEGEN_MODEL_FAST — быстрая/дешёвая модель для подсказок-чипов

Точные ID моделей смотрите в каталоге: https://routerai.ru/models
Примеры (слаги из каталога, сентябрь 2026):
  deepseek/deepseek-v4-pro-0813      ~97/293 ₽   — рабочий вариант
  anthropic/claude-sonnet-5          ~218/1093 ₽ — премиум-правки
  openai/gpt-5.6-sol                 ~218/1093 ₽
  google/gemini-3.1-pro-preview      ~218/1311 ₽
"""
import os
import re
import json
import time

import httpx


def _load_env():
    """Читает .env рядом с модулем (не перезаписывает существующие переменные)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

BASE_URL = os.environ.get("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1")
API_KEY = os.environ.get("ROUTERAI_API_KEY", "").strip()
MODEL = os.environ.get("SITEGEN_MODEL", "deepseek/deepseek-v4-pro-0813")
MODEL_FAST = os.environ.get("SITEGEN_MODEL_FAST", MODEL)


def is_configured() -> bool:
    return bool(API_KEY)


def chat(messages, model=None, temperature=0.7, max_tokens=6000,
         timeout=180.0, retries=2):
    """Возвращает текст ответа модели. Бросает RuntimeError при неудаче."""
    if not is_configured():
        raise RuntimeError("ROUTERAI_API_KEY не задан — работает демо-режим")
    payload = {
        "model": model or MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    last_err = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                r = client.post(f"{BASE_URL}/chat/completions",
                                json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"RouterAI: {last_err}")


def extract_json(text):
    """Достаёт JSON из ответа модели (терпит ```json-обёртки и лишний текст)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("JSON не найден в ответе модели")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i + 1])
    raise ValueError("Незакрытый JSON в ответе модели")
