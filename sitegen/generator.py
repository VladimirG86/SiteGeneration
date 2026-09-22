"""Пайплайн генерации и ИИ-правок сайта.

Генерация — 5 этапов (как у VERSTKA). Редактор — чат → ops-JSON (chat.py) →
перерендер. Каждая правка создаёт новую версию (undo до 12 шагов).
"""
import json
import os
import threading
import time
import uuid

import chat as chat_ops
import demo_content
import design
import llm
import prompts
import sections

SITES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sites")
os.makedirs(SITES_DIR, exist_ok=True)

STAGES = [
    {"key": "analyze", "title": "Анализируем ваш бизнес", "hint": "Определяем нишу и аудиторию"},
    {"key": "structure", "title": "Проектируем структуру", "hint": "Подбираем секции и порядок блоков"},
    {"key": "copy", "title": "Пишем тексты", "hint": "Заголовки, выгоды, ответы на возражения"},
    {"key": "build", "title": "Верстаем страницу", "hint": "Собираем секции в готовую страницу"},
    {"key": "art", "title": "Рисуем изображения", "hint": "Графика и оформление темы"},
]

MAX_VERSIONS = 12

_JOBS = {}
_LOCK = threading.Lock()


# ------------------------------------------------------------ файлы --------

def _paths(job_id):
    return {
        "site": os.path.join(SITES_DIR, f"{job_id}.json"),
        "html": os.path.join(SITES_DIR, f"{job_id}.html"),
        "hist": os.path.join(SITES_DIR, f"{job_id}.history.json"),
    }


def _load_site(job_id):
    p = _paths(job_id)["site"]
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_history(job_id):
    p = _paths(job_id)["hist"]
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_all(job_id: str, site: dict, html: str, push_version: bool):
    p = _paths(job_id)
    if push_version:
        hist = _load_history(job_id)
        hist.append(site)
        hist = hist[-MAX_VERSIONS:]
        with open(p["hist"], "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False)
    with open(p["site"], "w", encoding="utf-8") as f:
        json.dump(site, f, ensure_ascii=False)
    with open(p["html"], "w", encoding="utf-8") as f:
        f.write(html)


# ------------------------------------------------------------ статус -------

def get_site_html(job_id: str):
    job = _JOBS.get(job_id)
    if job and job.get("html"):
        return job["html"]
    p = _paths(job_id)["html"]
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read()
    return None


def get_version(job_id: str) -> int:
    return len(_load_history(job_id))


def get_job(job_id: str):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        return {
            "id": job_id,
            "status": job["status"],
            "stage": job["stage"],
            "stages": [s["title"] for s in STAGES],
            "hints": [s["hint"] for s in STAGES],
            "progress": round(job["stage"] / len(STAGES) * 100) if job["status"] != "done" else 100,
            "warning": job.get("warning"),
            "error": job.get("error"),
            "site_url": f"/api/site/{job_id}" if job["status"] == "done" else None,
        }


# ------------------------------------------------------------ генерация ----

def _llm_site(answers: dict, theme_mode: str, accent: str) -> dict:
    acc = design.ACCENTS[accent]
    messages = prompts.build_site_messages(answers, theme_mode, acc["label"], acc["main"])
    raw = llm.chat(messages, temperature=0.6, max_tokens=16000, timeout=240)
    site = llm.extract_json(raw)
    # Нормализация обязательна: сырой JSON от модели может содержать лишние
    # поля, пустые секции или мусор — рендерер должен получать только чистую
    # структуру. При битой структуре бросаем ValueError → run_job тихо
    # переключится на демо-генератор с warning для пользователя.
    site = chat_ops.normalize_site(site)
    if not site.get("brand") or not site.get("sections"):
        raise ValueError("Модель вернула некорректную структуру")
    return site


def run_job(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        return
    answers = job["answers"]
    theme_mode = job["theme"]["mode"]
    accent = job["theme"]["accent"]

    def finish_stage(min_seconds=1.4):
        time.sleep(min_seconds)

    try:
        # 1. Анализ
        _set_stage(job, 0)
        time.sleep(1.0)

        # 2–3. Структура + тексты (LLM или демо)
        warning = None
        if llm.is_configured():
            _set_stage(job, 1)
            try:
                site = _llm_site(answers, theme_mode, accent)
            except Exception as e:  # noqa: BLE001
                site = demo_content.build_site(answers, theme_mode, accent)
                warning = f"LLM недоступна ({e}) — сайт собран демо-генератором."
            finish_stage(0.6)
            _set_stage(job, 2)
            finish_stage(0.6)
        else:
            site = demo_content.build_site(answers, theme_mode, accent)
            _set_stage(job, 1)
            finish_stage(1.3)
            _set_stage(job, 2)
            finish_stage(1.3)

        # 4. Вёрстка
        _set_stage(job, 3)
        site["theme"] = {"mode": theme_mode, "accent": accent}
        site["features"] = site.get("features") or {"cart": False}
        html = sections.render_page(site, site_id=job_id)
        finish_stage(1.0)

        # 5. Изображения: hero-фото по смыслу бизнеса (если доступен RouterAI)
        _set_stage(job, 4)
        try:
            import images
            if images.is_configured() and images.generate_hero(site, job_id):
                html = sections.render_page(site, site_id=job_id)
        except Exception as e:  # noqa: BLE001 — картинки не критичны
            print(f"[IMG] hero skipped: {e}")
        finish_stage(0.5)

        job["html"] = html
        job["warning"] = warning
        job["status"] = "done"
        _save_all(job_id, site, html, push_version=True)
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)


def _set_stage(job, idx):
    job["stage"] = idx


def start_job(answers: dict, theme_mode: str, accent: str) -> str:
    job_id = uuid.uuid4().hex[:10]
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "status": "running",
            "stage": 0,
            "answers": answers,
            "theme": {"mode": theme_mode, "accent": accent},
            "chat": [],
            "created": time.time(),
        }
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return job_id


# ------------------------------------------------------------ редактор -----

def get_chat_history(job_id: str) -> list:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job:
            return list(job.get("chat", []))
    return []


def edit_site(job_id: str, user_msg: str) -> dict:
    """Применяет одну ИИ-правку: чат → ops → структура → перерендер."""
    with _LOCK:
        job = _JOBS.get(job_id)
    site = _load_site(job_id)
    if site is None:
        return {"error": "Сайт не найден"}
    history = get_chat_history(job_id)

    raw = llm.chat(
        chat_ops.build_editor_messages(site, history, user_msg),
        temperature=0.35, max_tokens=12000, timeout=240,
    )
    data = llm.extract_json(raw)
    reply = str(data.get("reply") or "").strip()[:600] or "Готово."
    ops = data.get("ops") if isinstance(data.get("ops"), list) else []
    if not ops:
        # правок нет — это просто ответ на вопрос; в историю, без версии
        _remember(job_id, user_msg, reply)
        return {"reply": reply, "applied": 0, "version": get_version(job_id), "ops": 0}

    # изображения генерируются отдельно (долго), остальное — через apply_ops
    struct_ops = [op for op in ops
                  if not (isinstance(op, dict) and op.get("op") == "gen_images")]
    gen_ops = [op for op in ops
               if isinstance(op, dict) and op.get("op") == "gen_images"]

    applied, notes = chat_ops.apply_ops(site, struct_ops)
    if gen_ops:
        import images as images_mod
        for g in gen_ops[:2]:
            target = g.get("target")
            count = g.get("count")
            count = int(count) if str(count or "").isdigit() else 6
            if target == "products":
                n = images_mod.generate_products(site, job_id, count)
                if n:
                    applied += 1
                else:
                    notes.append("фото товаров сгенерировать не удалось")
            elif target == "hero":
                if not images_mod.generate_hero(site, job_id):
                    notes.append("фото на первый экран сгенерировать не удалось")
                else:
                    applied += 1

    html = sections.render_page(site, site_id=job_id)
    _save_all(job_id, site, html, push_version=True)
    with _LOCK:
        job = _JOBS.get(job_id)
        if job:
            job["html"] = html
    _remember(job_id, user_msg,
              reply + (f" ({', '.join(notes)})" if notes else ""))
    return {"reply": reply, "applied": applied, "notes": notes,
            "version": get_version(job_id), "ops": len(ops)}


def _remember(job_id: str, user_msg: str, assistant_msg: str):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.setdefault("chat", []).append({"role": "user", "content": user_msg})
            job["chat"].append({"role": "assistant", "content": assistant_msg})
            job["chat"] = job["chat"][-10:]


def undo(job_id: str) -> dict:
    hist = _load_history(job_id)
    if len(hist) < 2:
        return {"error": "Отменять нечего — это первая версия"}
    hist.pop()  # текущая версия
    site = hist[-1]
    html = sections.render_page(site, site_id=job_id)
    _save_all(job_id, site, html, push_version=False)
    with open(_paths(job_id)["hist"], "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False)
    with _LOCK:
        job = _JOBS.get(job_id)
        if job:
            job["html"] = html
    return {"ok": True, "version": len(hist),
            "reply": "Отменил последнюю правку."}
