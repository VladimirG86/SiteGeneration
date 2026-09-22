"""Пайплайн генерации и ИИ-правок сайта.

Генерация — 5 этапов (как у VERSTKA). Редактор — чат → ops-JSON (chat.py) →
перерендер. Каждая правка создаёт новую версию (undo до 12 шагов).
История чата персистентна ({id}.chat.json) — переживает рестарт сервера.

Долгие правки можно слушать двумя способами:
  — опрос GET /api/chat/progress/{id} (фолбэк);
  — SSE-поток edit_site_stream(): start → progress* → done | error.

Данные лежат в SITEGEN_DATA_DIR (по умолчанию ./sites) — в Docker это volume.
"""
import json
import os
import queue
import threading
import time
import uuid

import chat as chat_ops
import demo_content
import design
import llm
import niches
import prompts
import sections

SITES_DIR = os.environ.get("SITEGEN_DATA_DIR") or \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "sites")
os.makedirs(SITES_DIR, exist_ok=True)

STAGES = [
    {"key": "analyze", "title": "Анализируем ваш бизнес", "hint": "Определяем нишу и аудиторию"},
    {"key": "structure", "title": "Проектируем структуру", "hint": "Подбираем секции и порядок блоков"},
    {"key": "copy", "title": "Пишем тексты", "hint": "Заголовки, выгоды, ответы на возражения"},
    {"key": "build", "title": "Верстаем страницу", "hint": "Собираем секции в готовую страницу"},
    {"key": "art", "title": "Рисуем изображения", "hint": "Графика и оформление темы"},
]

IMPORT_STAGES = [
    {"key": "fetch", "title": "Загружаем сайт", "hint": "Скачиваем страницу по ссылке"},
    {"key": "extract", "title": "Разбираем содержимое", "hint": "Вытаскиваем тексты, контакты и структуру"},
    {"key": "adapt", "title": "Переносим в конструктор", "hint": "ИИ переписывает под вашу тему"},
    {"key": "build", "title": "Верстаем страницу", "hint": "Собираем секции в готовую страницу"},
    {"key": "art", "title": "Готовим к редактору", "hint": "Финализируем и сохраняем"},
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
        "chat": os.path.join(SITES_DIR, f"{job_id}.chat.json"),
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


def _load_chat_file(job_id):
    p = _paths(job_id)["chat"]
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []
    return []


def _save_all(job_id: str, site: dict, html: str, push_version: bool):
    p = _paths(job_id)
    if push_version:
        hist = _load_history(job_id)
        hist.append(site)
        hist = hist[-MAX_VERSIONS:]
        with open(p["hist"], "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False)
        # s3 mirror history
        try:
            try:
                import storage as _st  # type: ignore
            except ImportError:
                import sitegen.storage as _st  # type: ignore
            if _st.is_s3():
                _st.save_bytes(f"sites/{job_id}.history.json", json.dumps(hist, ensure_ascii=False).encode())
        except Exception:
            pass
    with open(p["site"], "w", encoding="utf-8") as f:
        json.dump(site, f, ensure_ascii=False)
    with open(p["html"], "w", encoding="utf-8") as f:
        f.write(html)
    try:
        try:
            import storage as _st  # type: ignore
        except ImportError:
            import sitegen.storage as _st  # type: ignore
        if _st.is_s3():
            _st.save_bytes(f"sites/{job_id}.json", json.dumps(site, ensure_ascii=False).encode())
            _st.save_bytes(f"sites/{job_id}.html", html.encode())
    except Exception:
        pass


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


def get_site_dict(job_id: str):
    p = _paths(job_id)["site"]
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    job = _JOBS.get(job_id)
    if job and job.get("site"):
        return job["site"]
    return None


def get_version(job_id: str) -> int:
    return len(_load_history(job_id))


def get_job(job_id: str):
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        stages = IMPORT_STAGES if job.get("kind") == "import" else STAGES
        total = len(stages)
        return {
            "id": job_id,
            "status": job["status"],
            "stage": job["stage"],
            "kind": job.get("kind", "generate"),
            "source_url": job.get("source_url"),
            "stages": [s["title"] for s in stages],
            "hints": [s["hint"] for s in stages],
            "progress": round(job["stage"] / total * 100) if job["status"] != "done" else 100,
            "warning": job.get("warning"),
            "error": job.get("error"),
            "site_url": f"/api/site/{job_id}" if job["status"] == "done" else None,
        }


def get_progress(job_id: str) -> dict:
    """Прогресс долгой чат-правки (этап картинок). Пусто — нечего показывать."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job:
            return dict(job.get("progress") or {})
    return {}


def _set_progress(job_id: str, data: dict | None):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            if data:
                job["progress"] = data
            else:
                job.pop("progress", None)


# ------------------------------------------------------------ генерация ----

def _llm_site(answers: dict, theme_mode: str, accent: str) -> dict:
    acc = design.ACCENTS[accent]
    niche = niches.detect_niche(" ".join(str(v) for v in answers.values()))
    messages = prompts.build_site_messages(answers, theme_mode, acc["label"], acc["main"], niche)
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


def _llm_taplink(answers: dict, theme_mode: str, accent: str) -> dict:
    acc = design.ACCENTS[accent]
    messages = prompts.build_taplink_messages(answers, theme_mode, acc["label"], acc["main"])
    raw = llm.chat(messages, temperature=0.5, max_tokens=8000, timeout=120)
    site = llm.extract_json(raw)
    site = chat_ops.normalize_site(site)
    site["kind"] = "taplink"
    if not site.get("brand") or not site.get("sections"):
        raise ValueError("Модель вернула некорректную структуру taplink")
    return site


def _llm_vcard(answers: dict, theme_mode: str, accent: str) -> dict:
    acc = design.ACCENTS[accent]
    messages = prompts.build_vcard_messages(answers, theme_mode, acc["label"], acc["main"])
    raw = llm.chat(messages, temperature=0.5, max_tokens=8000, timeout=120)
    site = llm.extract_json(raw)
    site = chat_ops.normalize_site(site)
    site["kind"] = "vcard"
    if not site.get("brand") or not site.get("sections"):
        raise ValueError("Модель вернула некорректную структуру vcard")
    return site


def run_job(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        return
    answers = job["answers"]
    theme_mode = job["theme"]["mode"]
    accent = job["theme"]["accent"]
    kind = (job.get("site_kind") or job.get("kind") or "landing").lower()
    if kind not in ("landing", "taplink", "vcard"):
        kind = "landing"

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
                if kind == "taplink":
                    site = _llm_taplink(answers, theme_mode, accent)
                elif kind == "vcard":
                    site = _llm_vcard(answers, theme_mode, accent)
                else:
                    site = _llm_site(answers, theme_mode, accent)
            except Exception as e:  # noqa: BLE001
                if kind == "taplink":
                    site = demo_content.build_taplink_site(answers, theme_mode, accent)
                elif kind == "vcard":
                    site = demo_content.build_vcard_site(answers, theme_mode, accent)
                else:
                    site = demo_content.build_site(answers, theme_mode, accent)
                warning = f"LLM недоступна ({e}) — сайт собран демо-генератором."
            finish_stage(0.6)
            _set_stage(job, 2)
            finish_stage(0.6)
        else:
            if kind == "taplink":
                site = demo_content.build_taplink_site(answers, theme_mode, accent)
            elif kind == "vcard":
                site = demo_content.build_vcard_site(answers, theme_mode, accent)
            else:
                site = demo_content.build_site(answers, theme_mode, accent)
            _set_stage(job, 1)
            finish_stage(1.3)
            _set_stage(job, 2)
            finish_stage(1.3)

        # 4. Вёрстка
        _set_stage(job, 3)
        site["theme"] = {"mode": theme_mode, "accent": accent}
        site["kind"] = kind
        site["features"] = site.get("features") or {"cart": False}
        chat_ops.ensure_ids(site)
        html = sections.render_page(site, site_id=job_id)
        finish_stage(1.0)

        # 5. Изображения: hero-фото по смыслу бизнеса (если доступен RouterAI) — только для лендинга
        _set_stage(job, 4)
        try:
            import images
            if kind == "landing" and images.is_configured() and images.generate_hero(site, job_id):
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


def start_job(answers: dict, theme_mode: str, accent: str, site_kind: str = "landing") -> str:
    if site_kind not in ("landing", "taplink", "vcard"):
        site_kind = "landing"
    job_id = uuid.uuid4().hex[:10]
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "kind": "generate",
            "site_kind": site_kind,
            "status": "running",
            "stage": 0,
            "answers": answers,
            "theme": {"mode": theme_mode, "accent": accent},
            "chat": [],
            "created": time.time(),
        }
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    return job_id


# ------------------------------------------------------------ импорт ----

def run_import_job(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        return
    url = job.get("source_url", "")
    theme_mode = job["theme"]["mode"]
    accent = job["theme"]["accent"]
    try:
        # 0. Загружаем
        _set_stage(job, 0)
        time.sleep(0.6)
        import importer
        html, final_url = importer.fetch_html(url)
        # 1. Разбираем
        _set_stage(job, 1)
        signals = importer.extract_signals(html, final_url)
        # sitemap: догружаем до 5 доп. страниц (не критично)
        try:
            importer.augment_signals_with_sitemap(signals, final_url, max_extra=5)
        except Exception as e:  # noqa: BLE001
            print(f"[IMPORT] sitemap skipped: {e}")
        time.sleep(0.5)
        # 2. Адаптируем (LLM или эвристика)
        _set_stage(job, 2)
        warning = None
        try:
            site = importer.build_llm_site(signals, theme_mode, accent)
        except Exception as e:  # noqa: BLE001
            site = importer.heuristic_site(signals, theme_mode, accent)
            # нормализуем уже внутри heuristic, но на случай
            site = chat_ops.normalize_site(site)
            warning = f"ИИ-перенос с оговорками ({e}) — проверьте тексты."
        time.sleep(0.4)
        # 3. Вёрстка
        _set_stage(job, 3)
        # финальный акцент: importer мог подобрать автопалитру — уважаем её
        final_accent = site.get("theme", {}).get("accent") or accent
        # если импорт вернул purple а у нас были яркие цвета — пробуем подобрать
        if final_accent == "purple" and accent == "purple":
            picked = importer.pick_accent_from_colors(signals.get("colors") or [])
            if picked:
                final_accent = picked
        site["theme"] = {"mode": theme_mode, "accent": final_accent}
        job["theme"]["accent"] = final_accent  # чтобы /api/job отражал реальный
        site["import_source"] = final_url
        site["features"] = site.get("features") or {"cart": False}
        # пробуем подтянуть оригинальное фото (не критично, тихо)
        try:
            importer.try_attach_original_images(site, signals, job_id)
        except Exception as e:  # noqa: BLE001
            print(f"[IMPORT] image attach skipped: {e}")
        chat_ops.ensure_ids(site)
        html_out = sections.render_page(site, site_id=job_id)
        time.sleep(0.6)
        # 4. Финализация
        _set_stage(job, 4)
        time.sleep(0.4)
        job["html"] = html_out
        job["warning"] = warning
        job["status"] = "done"
        _save_all(job_id, site, html_out, push_version=True)
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)


def start_import_job(source_url: str, theme_mode: str = "light", accent: str = "purple") -> str:
    if theme_mode not in design.MODES:
        theme_mode = "light"
    if accent not in design.ACCENTS:
        accent = "purple"
    job_id = uuid.uuid4().hex[:10]
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "kind": "import",
            "status": "running",
            "stage": 0,
            "source_url": source_url,
            "theme": {"mode": theme_mode, "accent": accent},
            "chat": [],
            "created": time.time(),
        }
    threading.Thread(target=run_import_job, args=(job_id,), daemon=True).start()
    return job_id


# ------------------------------------------------------------ редактор -----

def get_chat_history(job_id: str) -> list:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job and job.get("chat"):
            return list(job["chat"])
    # в памяти пусто (рестарт сервера) — читаем с диска
    return _load_chat_file(job_id)


def _do_edit(job_id: str, user_msg: str, images_cb=None) -> dict:
    """Ядро правки: чат → ops → структура → перерендер.

    images_cb(stage, done, total, target) вызывается на этапах картинок
    (или None). Возвращает result-словарь; {"error": ...} — сайт не найден.
    Исключения LLM/сети пробрасываются вызывающему.
    """
    site = _load_site(job_id)
    if site is None:
        return {"error": "Сайт не найден"}
    chat_ops.ensure_ids(site)  # миграция сайтов, созданных до введения id
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
            count = max(1, min(count, 8))
            if target == "products":
                if images_cb:
                    images_cb("images", 0, count, "products")

                def _cb(d, t, _cb2=images_cb):
                    if _cb2:
                        _cb2("images", d, t, "products")

                n = images_mod.generate_products(site, job_id, count, on_progress=_cb)
                if n:
                    applied += 1
                else:
                    notes.append("фото товаров сгенерировать не удалось")
            elif target == "hero":
                if images_cb:
                    images_cb("images", 0, 1, "hero")
                ok = images_mod.generate_hero(site, job_id)
                if images_cb:
                    images_cb("images", 1 if ok else 0, 1, "hero")
                if not ok:
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


def edit_site(job_id: str, user_msg: str) -> dict:
    """Синхронная правка (POST /api/chat). Прогресс — через /api/chat/progress."""
    _set_progress(job_id, {"stage": "llm", "done": 0, "total": 1})
    try:
        return _do_edit(
            job_id, user_msg,
            images_cb=lambda st, d, t, tgt: _set_progress(
                job_id, {"stage": st, "done": d, "total": t, "target": tgt}))
    finally:
        _set_progress(job_id, None)


def edit_site_stream(job_id: str, user_msg: str):
    """SSE-поток правки: yield (event, data).

    События: start → progress* → done | error. Между ними — ping каждые ~15 c
    простоя (keep-alive для прокси). Правка выполняется в worker-потоке,
    генератор разгребает очередь — клиент получает события в реальном времени.
    """
    q = queue.Queue()

    def _cb(st, d, t, tgt):
        payload = {"stage": st, "done": d, "total": t, "target": tgt}
        q.put(("progress", payload))
        _set_progress(job_id, payload)  # опросный фолбэк тоже живёт

    outcome = {}

    def _work():
        try:
            outcome["result"] = _do_edit(job_id, user_msg, images_cb=_cb)
        except Exception as e:  # noqa: BLE001 — отдадим событием error
            outcome["error"] = str(e)
        finally:
            _set_progress(job_id, None)
            q.put((None, None))  # sentinel

    threading.Thread(target=_work, daemon=True).start()
    yield ("start", {"job": job_id})
    idle = 0
    while True:
        try:
            ev, data = q.get(timeout=1.0)
        except queue.Empty:
            idle += 1
            if idle >= 15:
                yield ("ping", {})
                idle = 0
            continue
        idle = 0
        if ev is None:
            break
        yield (ev, data)
    if "error" in outcome:
        yield ("error", {"error": outcome["error"]})
    else:
        yield ("done", outcome.get("result", {"error": "пустой результат"}))


def _remember(job_id: str, user_msg: str, assistant_msg: str):
    pair = [{"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_msg}]
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.setdefault("chat", []).extend(pair)
            job["chat"] = job["chat"][-10:]
    # персистентность: история переживает рестарт сервера
    try:
        hist = _load_chat_file(job_id)
        hist.extend(pair)
        hist = hist[-10:]
        with open(_paths(job_id)["chat"], "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False)
    except OSError:
        pass


def undo(job_id: str) -> dict:
    hist = _load_history(job_id)
    if len(hist) < 2:
        return {"error": "Отменять нечего — это первая версия"}
    hist.pop()  # текущая версия
    site = hist[-1]
    chat_ops.ensure_ids(site)
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
