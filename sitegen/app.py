"""Прототип ИИ-конструктора сайтов (аналог VERSTKA.ai) — API-сервер.

Запуск:
  uvicorn app:app --host 0.0.0.0 --port 8000
  docker compose up --build   # прод-подобный стенд (см. README)

Ключ RouterAI читается из .env (или переменных окружения) — см. llm.py.
Без ключа работает демо-режим (demo_content.py).

Защита (базовая, для прототипа):
  — rate-limit по IP на генерацию/чат/анализ/заявки/авторизацию;
  — /api/leads закрывается токеном, если задан SITEGEN_ADMIN_TOKEN;
  — id сайтов валидируются (защита от path traversal);
  — вход по email-коду: SMTP (боевой) или демо-код на фронте.
"""
import json
import os
import re
import secrets
import smtplib
import threading
import time
from email.message import EmailMessage

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import design
import generator
import llm
import niches

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMIN_TOKEN = os.environ.get("SITEGEN_ADMIN_TOKEN", "").strip()

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@sborka.ai").strip()

AUTH_CODE_TTL = 600       # код живёт 10 минут
AUTH_RESEND_COOLDOWN = 44  # как таймер на фронте
AUTH_MAX_FAILS = 5

app = FastAPI(title="SiteGen prototype")


def auth_enabled() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS and SMTP_FROM)


# ------------------------------------------------------- rate limiting ----

# bucket -> (запросов, за секунд). Хранилище в памяти — для прототипа
# достаточно; в проде заменить на Redis (см. README).
RATE_LIMITS = {
    "generate": (10, 3600),   # генерация сайта — дорогая, 10/час с IP
    "chat": (60, 3600),       # ИИ-правки — 60/час
    "analyze": (120, 3600),   # чипы-подсказки
    "lead": (120, 3600),      # заявки с сайтов
    "auth": (30, 3600),       # email-коды
    "import": (20, 3600),     # импорт по URL
    "export": (60, 3600),
    "publish": (20, 3600),
}
_RATE = {}
_RATE_LOCK = threading.Lock()


def _limited(request: Request | None, bucket: str) -> bool:
    limit, window = RATE_LIMITS[bucket]
    ip = request.client.host if request and request.client else "?"
    now = time.time()
    key = (ip, bucket)
    with _RATE_LOCK:
        ts = [t for t in _RATE.get(key, []) if now - t < window]
        if len(ts) >= limit:
            _RATE[key] = ts
            return True
        ts.append(now)
        _RATE[key] = ts
        return False


def _too_many(bucket: str):
    return JSONResponse(
        {"error": f"Слишком много запросов ({bucket}). Подождите и попробуйте снова."},
        status_code=429)


def _valid_job_id(job_id: str) -> bool:
    return isinstance(job_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", job_id) is not None


def _no_job():
    return JSONResponse({"error": "job not found"}, status_code=404)


# ------------------------------------------------------------------ схемы ---

class AnalyzeIn(BaseModel):
    name: str = ""
    about: str = Field(min_length=3, max_length=2000)


class GenerateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    about: str = Field(min_length=10, max_length=2000)
    products: str = Field(default="", max_length=2000)
    advantages: str = Field(default="", max_length=2000)
    extras: str = Field(default="", max_length=2000)
    theme_mode: str = Field(default="light")
    accent: str = Field(default="purple")
    email: str = Field(default="", max_length=120)


class LeadIn(BaseModel):
    name: str = ""
    phone: str = ""
    comment: str = ""
    type: str = ""            # "form" | "cart"
    items: list = Field(default_factory=list)  # позиции заказа из корзины


class ChatIn(BaseModel):
    message: str = Field(min_length=2, max_length=1200)


class AuthCodeIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)


class AuthVerifyIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    code: str = Field(min_length=6, max_length=6)


class ImportIn(BaseModel):
    url: str = Field(min_length=5, max_length=2048)
    theme_mode: str = Field(default="light")
    accent: str = Field(default="purple")


class WpPublishIn(BaseModel):
    wp_url: str = Field(min_length=5, max_length=2048)
    username: str = Field(min_length=1, max_length=120)
    app_password: str = Field(min_length=4, max_length=256)
    status: str = Field(default="draft")  # draft | publish


# ------------------------------------------------------------------- api ----

@app.get("/api/config")
def config():
    import images
    return {
        "llm": llm.is_configured(),
        "model": llm.MODEL if llm.is_configured() else None,
        "editor": llm.is_configured(),
        "images": images.is_configured(),
        "auth": auth_enabled(),
        "accents": [{"id": k, "label": v["label"], "hex": v["main"]} for k, v in design.ACCENTS.items()],
        "modes": list(design.MODES),
    }


@app.post("/api/analyze")
def analyze(body: AnalyzeIn, request: Request):
    """После шага «О бизнесе»: определяем нишу и отдаём подсказки-чипы."""
    if _limited(request, "analyze"):
        return _too_many("analyze")
    niche = niches.detect_niche(f"{body.name} {body.about}")
    chips = niches.chips_for(niche)
    if llm.is_configured():
        try:
            import prompts
            raw = llm.chat(prompts.build_chips_messages(
                {"Компания": body.name, "Описание": body.about}),
                model=llm.MODEL_FAST, temperature=0.8, max_tokens=1500, timeout=60)
            data = llm.extract_json(raw)
            merged = {}
            for key in ("products", "advantages", "extras"):
                items = [str(x).strip()[:48] for x in (data.get(key) or [])
                         if isinstance(x, str) and 2 < len(str(x).strip()) <= 48]
                merged[key] = (items + chips[key])[:9]
            chips = merged
        except Exception:  # noqa: BLE001 — тихо падаем в демо-чипы
            pass
    return {"niche": niche, "chips": chips}


@app.post("/api/generate")
def generate(body: GenerateIn, request: Request):
    if _limited(request, "generate"):
        return _too_many("generate")
    if body.theme_mode not in design.MODES:
        body.theme_mode = "light"
    if body.accent not in design.ACCENTS:
        body.accent = "purple"
    answers = {
        "Название": body.name,
        "О бизнесе": body.about,
        "Услуги/товары": body.products,
        "Преимущества": body.advantages,
        "Дополнительно": body.extras,
    }
    job_id = generator.start_job(answers, body.theme_mode, body.accent)
    return {"job_id": job_id}


@app.post("/api/import")
def import_site(body: ImportIn, request: Request):
    """Импорт произвольного сайта по URL: валидация -> фоновая задача."""
    if _limited(request, "import"):
        return _too_many("import")
    if body.theme_mode not in design.MODES:
        body.theme_mode = "light"
    if body.accent not in design.ACCENTS:
        body.accent = "purple"
    try:
        import importer
        url = importer.validate_url(body.url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    job_id = generator.start_import_job(url, body.theme_mode, body.accent)
    return {"job_id": job_id, "source_url": url}


@app.get("/api/export/{job_id}")
def export_site(job_id: str, request: Request):
    """Экспорт сайта: ZIP с index.html (+ инструкция для заливки на свой хостинг)."""
    if _limited(request, "export"):
        return _too_many("export")
    if not _valid_job_id(job_id):
        return _no_job()
    html = generator.get_site_html(job_id)
    if not html:
        return _no_job()
    import io
    import zipfile
    site = generator.get_site_dict(job_id) or {}
    brand = (site.get("brand") or job_id).strip()[:40] or job_id
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", html)
        readme = (
            f"Сайт: {brand}\n"
            f"Экспорт из СБОРКА — {job_id}\n\n"
            "Как залить на свой хостинг:\n"
            "1. Распакуйте архив в корень сайта (где лежит index.html).\n"
            "2. Загрузите index.html по FTP/SFTP или через панель хостинга.\n"
            "3. Сайт — один самодостаточный файл: картинки встроены как data-URI, шрифты — Google Fonts.\n"
            "4. Форма заявок по умолчанию шлёт на /api/lead — замените action на свой обработчик или оставьте как есть если оставляете у нас.\n"
        )
        z.writestr("README.txt", readme)
    buf.seek(0)
    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="site-{job_id}.zip"'},
    )


@app.post("/api/publish/wp/{job_id}")
def publish_wp(job_id: str, body: WpPublishIn, request: Request):
    """Публикация в WordPress: создаёт страницу через WP REST API.

    Если у сайта есть локальные hero/prod картинки (data-URI в HTML),
    пытаемся загрузить их в медиабиблиотеку WP (/wp-json/wp/v2/media)
    и подменить data-URI на URL из WP — страница становится лёгкой и
    картинки попадают в медиатеку.
    """
    if _limited(request, "publish"):
        return _too_many("publish")
    if not _valid_job_id(job_id):
        return _no_job()
    html = generator.get_site_html(job_id)
    if not html:
        return _no_job()
    site = generator.get_site_dict(job_id) or {}
    try:
        import importer
        wp_base = importer._validate_wp_url(body.wp_url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    status = body.status.strip().lower()
    if status not in ("draft", "publish", "private"):
        status = "draft"
    title = (site.get("brand") or "Сайт из СБОРКА")[:120]

    import base64
    import httpx
    creds = base64.b64encode(f"{body.username}:{body.app_password}".encode()).decode()
    auth_h = f"Basic {creds}"
    wp_base = wp_base.rstrip("/")

    # --- попробуем залить медиа (hero + prod) ---
    # html будет мутировать: data-URI -> WP URL
    html_for_wp = html
    media_featured_id = None
    try:
        import images as images_mod
        import os as _os
        # соберём файлы которые реально есть
        candidates = []
        hero_path = _os.path.join(images_mod.ASSETS_DIR, job_id, "hero.webp")
        if _os.path.exists(hero_path):
            candidates.append(("hero.webp", hero_path))
        # prod images
        prod_dir = _os.path.join(images_mod.ASSETS_DIR, job_id)
        if _os.path.isdir(prod_dir):
            for fn in sorted(_os.listdir(prod_dir)):
                if fn.startswith("prod_") and fn.endswith(".webp"):
                    candidates.append((fn, _os.path.join(prod_dir, fn)))
        # ограничим 4 файла чтобы не долго (hero + 3 товара)
        for fname, fpath in candidates[:4]:
            try:
                with open(fpath, "rb") as fh:
                    data = fh.read()
                if not data or len(data) > 5_000_000:
                    continue
                data_uri = images_mod.data_uri(job_id, fname)
                # грузим в WP
                with httpx.Client(timeout=25.0) as cl:
                    r = cl.post(
                        wp_base + "/wp-json/wp/v2/media",
                        content=data,
                        headers={
                            "Authorization": auth_h,
                            "Content-Disposition": f'attachment; filename="{fname}"',
                            "Content-Type": "image/webp",
                        },
                    )
                    r.raise_for_status()
                    j = r.json()
                    media_url = j.get("source_url") or j.get("guid", {}).get("rendered")
                    media_id = j.get("id")
                    if media_url and data_uri and data_uri in html_for_wp:
                        html_for_wp = html_for_wp.replace(data_uri, media_url, 1)
                    if fname == "hero.webp" and media_id and not media_featured_id:
                        media_featured_id = media_id
            except Exception as me:  # noqa: BLE001 — медиа не критично, тихо
                print(f"[WP-MEDIA] {fname} upload skipped: {me}")
                continue
    except Exception as e:  # noqa: BLE001
        print(f"[WP-MEDIA] skip: {e}")

    wp_content = f"<!-- wp:html -->\n{html_for_wp}\n<!-- /wp:html -->"
    payload = {"title": title, "content": wp_content, "status": status}
    if media_featured_id:
        payload["featured_media"] = media_featured_id
    headers = {"Authorization": auth_h, "Content-Type": "application/json"}
    endpoint = wp_base + "/wp-json/wp/v2/pages"
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.post(endpoint, json=payload, headers=headers)
            if r.status_code == 404:
                endpoint2 = wp_base + "/wp-json/wp/v2/posts"
                r = client.post(endpoint2, json=payload, headers=headers)
                endpoint = endpoint2
            r.raise_for_status()
            data = r.json()
            link = data.get("link") or data.get("guid", {}).get("rendered") or wp_base
            out = {"ok": True, "url": link, "id": data.get("id"), "endpoint": endpoint}
            if media_featured_id:
                out["featured_media"] = media_featured_id
            return out
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else "?"
        detail = ""
        try:
            j = e.response.json()
            detail = j.get("message") or str(j)[:400]
        except Exception:
            detail = (e.response.text[:400] if e.response is not None else "")
        return JSONResponse({"error": f"WordPress вернул HTTP {code}: {detail}"}, status_code=502)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Не удалось связаться с WordPress: {e}"}, status_code=502)


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    if not _valid_job_id(job_id):
        return _no_job()
    job = generator.get_job(job_id)
    if not job:
        return _no_job()
    return job


@app.get("/api/site/{job_id}", response_class=HTMLResponse)
def site_page(job_id: str):
    if not _valid_job_id(job_id):
        return HTMLResponse("<h1>Сайт не найден</h1>", status_code=404)
    html = generator.get_site_html(job_id)
    if not html:
        return HTMLResponse("<h1>Сайт ещё не готов</h1>", status_code=404)
    return HTMLResponse(html)


# -------------------------------------------------------------- редактор ----

@app.post("/api/chat/{job_id}")
def chat_edit(job_id: str, body: ChatIn, request: Request):
    if _limited(request, "chat"):
        return _too_many("chat")
    if not _valid_job_id(job_id):
        return _no_job()
    if not llm.is_configured():
        return JSONResponse({"error": "Редактору нужен ключ RouterAI (.env)"}, status_code=503)
    try:
        result = generator.edit_site(job_id, body.message)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Ошибка ИИ-правки: {e}"}, status_code=502)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return result


@app.get("/api/chat/stream/{job_id}")
def chat_stream(job_id: str, request: Request, message: str = ""):
    """SSE-поток правки (EventSource): start → progress* → done | error.

    Между событиями — ping каждые ~15 c. Ошибка валидации — обычный JSON
    с 4xx (фронт в этом случае откатывается на POST /api/chat).
    """
    if _limited(request, "chat"):
        return _too_many("chat")
    if not _valid_job_id(job_id):
        return _no_job()
    msg = (message or "").strip()
    if not (2 <= len(msg) <= 1200):
        return JSONResponse({"error": "message: 2..1200 символов"}, status_code=400)
    if generator.get_site_html(job_id) is None:
        return _no_job()
    if not llm.is_configured():
        return JSONResponse({"error": "Редактору нужен ключ RouterAI (.env)"}, status_code=503)

    def _gen():
        for ev, data in generator.edit_site_stream(job_id, msg):
            yield f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/chat/progress/{job_id}")
def chat_progress(job_id: str):
    """Прогресс долгой правки (генерация картинок). Фронт опрашивает,
    пока ждёт ответ /api/chat. Пустой объект — показывать нечего."""
    if not _valid_job_id(job_id):
        return {}
    return generator.get_progress(job_id)


@app.post("/api/undo/{job_id}")
def undo_edit(job_id: str):
    if not _valid_job_id(job_id):
        return _no_job()
    result = generator.undo(job_id)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result


# --------------------------------------------------------------- заявки -----

_LEAD_LOCK = threading.Lock()


def _leads_path(site_id: str):
    if not _valid_job_id(site_id):
        return None
    return os.path.join(generator.SITES_DIR, f"{site_id}.leads.json")


def _read_leads(site_id: str) -> list:
    p = _leads_path(site_id)
    if not p or not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


@app.post("/api/lead/{site_id}")
def lead(site_id: str, body: LeadIn, request: Request):
    if _limited(request, "lead"):
        return _too_many("lead")
    p = _leads_path(site_id)
    if not p:
        return JSONResponse({"error": "bad site id"}, status_code=400)
    with _LEAD_LOCK:
        leads = _read_leads(site_id)
        leads.append(body.model_dump())
        with open(p, "w", encoding="utf-8") as f:
            json.dump(leads, f, ensure_ascii=False)
    tag = "CART" if body.type == "cart" else "LEAD"
    print(f"[{tag}] site={site_id} {body.model_dump()}")
    return {"ok": True}


@app.get("/api/leads/{site_id}")
def leads(site_id: str, request: Request):
    if ADMIN_TOKEN:
        got = request.query_params.get("token") or request.headers.get("x-admin-token")
        if got != ADMIN_TOKEN:
            return JSONResponse({"error": "Нужен admin-токен"}, status_code=401)
    if not _valid_job_id(site_id):
        return JSONResponse({"error": "bad site id"}, status_code=400)
    with _LEAD_LOCK:
        return _read_leads(site_id)


# ----------------------------------------------------------- авторизация ----

_AUTH_CODES = {}  # email -> {"code","exp","sent","fails"}
_AUTH_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def _send_code_email(to_email: str, code: str):
    msg = EmailMessage()
    msg["Subject"] = f"Ваш код для СБОРКА: {code}"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(
        f"Код для создания сайта: {code}\n\n"
        f"Действует {AUTH_CODE_TTL // 60} минут. "
        f"Если вы не запрашивали код — проигнорируйте письмо.")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


@app.post("/api/auth/code")
def auth_code(body: AuthCodeIn, request: Request):
    """Отправить 6-значный код на email. Без SMTP — 503 (фронт уйдёт в демо)."""
    if _limited(request, "auth"):
        return _too_many("auth")
    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        return JSONResponse({"error": "Похоже, в адресе почты ошибка"}, status_code=400)
    if not auth_enabled():
        return JSONResponse({"error": "SMTP не настроен — доступен только демо-режим"},
                            status_code=503)
    now = time.time()
    with _AUTH_LOCK:
        prev = _AUTH_CODES.get(email)
        if prev and now - prev["sent"] < AUTH_RESEND_COOLDOWN:
            wait = int(AUTH_RESEND_COOLDOWN - (now - prev["sent"]))
            return JSONResponse({"error": "Код уже отправлен", "retry_after": wait},
                                status_code=429)
    code = f"{secrets.randbelow(900000) + 100000}"
    try:
        _send_code_email(email, code)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Не удалось отправить письмо: {e}"}, status_code=502)
    with _AUTH_LOCK:
        _AUTH_CODES[email] = {"code": code, "exp": now + AUTH_CODE_TTL,
                              "sent": now, "fails": 0}
    return {"ok": True, "cooldown": AUTH_RESEND_COOLDOWN}


@app.post("/api/auth/verify")
def auth_verify(body: AuthVerifyIn, request: Request):
    """Проверить код. Без SMTP — 503."""
    if _limited(request, "auth"):
        return _too_many("auth")
    email = body.email.strip().lower()
    if not auth_enabled():
        return JSONResponse({"error": "SMTP не настроен — доступен только демо-режим"},
                            status_code=503)
    now = time.time()
    with _AUTH_LOCK:
        rec = _AUTH_CODES.get(email)
        if not rec or now > rec["exp"]:
            return JSONResponse({"error": "Код не найден или истёк — запросите новый"},
                                status_code=400)
        if rec["fails"] >= AUTH_MAX_FAILS:
            return JSONResponse({"error": "Слишком много попыток — запросите новый код"},
                                status_code=429)
        if not secrets.compare_digest(body.code.strip(), rec["code"]):
            rec["fails"] += 1
            return JSONResponse({"error": "Неверный код"}, status_code=400)
        del _AUTH_CODES[email]
    return {"ok": True}


# --------------------------------------------------------------- static ----

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


if not ADMIN_TOKEN:
    print("[WARN] SITEGEN_ADMIN_TOKEN не задан — /api/leads открыт всем. "
          "Для публичного стенда задайте токен в .env")
if not auth_enabled():
    print("[INFO] SMTP не настроен — вход по email-коду работает в демо-режиме")
