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
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@nelvi.app").strip()

# Nelvi prod
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
BASE_URL = os.environ.get("BASE_URL", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
DOMAIN = os.environ.get("DOMAIN", "").strip() or os.environ.get("SITEGEN_DOMAIN", "").strip()

# простая модерация — список стоп-слов (можно расширять, в проде — LLM-модерация)
_BANNED_SUBSTR = ["спайс", "наркоти", "порно", "casino", "казино"]
def _moderate_text(text: str) -> str | None:
    low = (text or "").lower()
    for w in _BANNED_SUBSTR:
        if w in low:
            return w
    return None

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
    "billing": (20, 86400),   # биллинг/тарифы
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
    kind: str = Field(default="landing", max_length=20)  # landing | vcard (taplink → vcard alias, QR-визитка покрывает мультиссылку)


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
    try:
        try:
            import storage as st  # type: ignore
        except ImportError:
            import sitegen.storage as st  # type: ignore
        s3_on = bool(getattr(st, "S3_BUCKET", "") and st.is_s3())
        s3_bucket = getattr(st, "S3_BUCKET", "") if s3_on else ""
    except Exception:
        s3_on = False
        s3_bucket = ""
    # prod flags
    pg_on = bool(DATABASE_URL)
    redis_on = bool(REDIS_URL)
    tg_on = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    return {
        "llm": llm.is_configured(),
        "model": llm.MODEL if llm.is_configured() else None,
        "editor": llm.is_configured(),
        "images": images.is_configured(),
        "auth": auth_enabled(),
        "accents": [{"id": k, "label": v["label"], "hex": v["main"]} for k, v in design.ACCENTS.items()],
        "modes": list(design.MODES),
        "kinds": ["landing", "vcard", "canvas"],
        "s3": s3_on,
        "s3_bucket": s3_bucket,
        "postgres": pg_on,
        "redis": redis_on,
        "telegram": tg_on,
        "base_url": BASE_URL,
        "domain": DOMAIN,
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
    kind = (body.kind or "landing").strip().lower()
    # taplink убран: QR-визитка (vcard) покрывает мультиссылку; старый kind мапим в vcard
    if kind == "taplink":
        kind = "vcard"
    if kind not in ("landing", "vcard", "canvas"):
        kind = "landing"
    answers = {
        "Название": body.name,
        "О бизнесе": body.about,
        "Услуги/товары": body.products,
        "Преимущества": body.advantages,
        "Дополнительно": body.extras,
    }
    # модерация (лёгкая, до LLM чтобы не тратить токены)
    combined = " ".join([body.name, body.about, body.products, body.advantages, body.extras])
    bad = _moderate_text(combined)
    if bad:
        return JSONResponse({"error": f"Контент отклонён модерацией (найдено: {bad}) — проверьте формулировки"}, status_code=400)
    # canvas — отдельный флоу: создаём пустой канвас без LLM, сразу готово
    if kind == "canvas":
        import uuid, json as _j
        job_id = uuid.uuid4().hex[:8]
        # ensure unique
        while os.path.exists(os.path.join(generator.SITES_DIR, f"{job_id}.html")) or os.path.exists(os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")):
            job_id = uuid.uuid4().hex[:8]
        brand = body.name.strip()[:60] or "Nelvi Canvas"
        site = {"brand": brand, "kind": "canvas", "theme": {"mode": body.theme_mode, "accent": body.accent}, "sections": [], "canvas_blocks": []}
        # default blocks with brand
        default_blocks=[
            {"id":"h1","type":"heading","x":48,"y":48,"w":520,"h":84,"z":1,"props":{"text": brand, "size":36,"color":"#2B2B36"}},
            {"id":"t1","type":"text","x":48,"y":148,"w":520,"h":72,"z":2,"props":{"text": body.about.strip()[:160] or "Собирай страницы блоками, публикуй в один клик.", "size":15,"color":"#7A7A8E"}},
            {"id":"b1","type":"button","x":48,"y":240,"w":180,"h":44,"z":3,"props":{"text":"Попробовать →","bg":"#5B5FEF","color":"#fff","radius":10}},
        ]
        site["canvas_blocks"]=default_blocks
        # save canvas file
        try:
            os.makedirs(CANVAS_DIR, exist_ok=True)
            with open(os.path.join(CANVAS_DIR, f"canvas-{job_id}.json"), "w", encoding="utf-8") as f:
                _j.dump({"blocks": default_blocks}, f, ensure_ascii=False)
        except Exception: pass
        html, _ = _canvas_build_html(job_id, default_blocks, site)
        generator._save_all(job_id, site, html, push_version=True)
        # also create fake job entry so /api/job works
        try:
            import generator as _gen
            with _gen._LOCK:
                _gen._JOBS[job_id]={"id": job_id, "kind":"canvas","site_kind":"canvas","status":"done","stage":5,"answers":answers,"theme":{"mode":body.theme_mode,"accent":body.accent},"stage_done":True}
        except Exception: pass
        return {"job_id": job_id, "kind": "canvas"}
    job_id = generator.start_job(answers, body.theme_mode, body.accent, site_kind=kind)
    return {"job_id": job_id, "kind": kind}


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
            f"Экспорт из Nelvi — {job_id}\n\n"
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
    title = (site.get("brand") or "Сайт из Nelvi")[:120]

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


@app.get("/api/site/{job_id}/sitemap.xml")
def site_sitemap(job_id: str, request: Request):
    if not _valid_job_id(job_id):
        return HTMLResponse("not found", status_code=404)
    site = generator.get_site_dict(job_id)
    if not site:
        return HTMLResponse("not found", status_code=404)
    base = str(request.base_url).rstrip("/")
    # prefer public Pages url if available, else base
    loc = f"{base}/api/site/{job_id}"
    # for SEO: include section anchors for landing (Google ignores fragments but useful for hint)
    urls = [loc]
    # add anchors for landing sections (optional, sitemap spec allows but fragments usually ignored)
    # keep single entry for simplicity
    lastmod = time.strftime("%Y-%m-%d")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url>
</urlset>"""
    from fastapi.responses import Response
    return Response(content=xml.encode(), media_type="application/xml; charset=utf-8")


@app.get("/api/site/{job_id}/robots.txt")
def site_robots(job_id: str, request: Request):
    if not _valid_job_id(job_id):
        return HTMLResponse("not found", status_code=404)
    if not generator.get_site_dict(job_id):
        return HTMLResponse("not found", status_code=404)
    base = str(request.base_url).rstrip("/")
    sitemap_url = f"{base}/api/site/{job_id}/sitemap.xml"
    txt = f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n"
    from fastapi.responses import Response
    return Response(content=txt.encode(), media_type="text/plain; charset=utf-8")


@app.get("/api/site/{job_id}/vcard")
def site_vcard(job_id: str, request: Request):
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    site = generator.get_site_dict(job_id)
    if not site:
        return _no_job()
    brand = (site.get("brand") or "Contact").strip()[:80]
    phone = (site.get("phone") or "").strip()
    email = (site.get("email") or "").strip()
    address = (site.get("address") or "").strip()
    # try to enrich from vcard sections
    for s in (site.get("sections") or []):
        if s.get("type") == "vcard":
            for it in (s.get("items") or []):
                lbl = (it.get("label") or "").lower()
                val = (it.get("value") or it.get("text") or "").strip()
                if not val:
                    continue
                if "тел" in lbl or "phone" in lbl and not phone:
                    phone = val
                if "mail" in lbl or "почт" in lbl and not email:
                    email = val
                if "адрес" in lbl or "address" in lbl and not address:
                    address = val
        if s.get("type") == "qrcode" and not phone and site.get("phone"):
            phone = site.get("phone")
    # fallback to extras
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{brand}"]
    if brand:
        # N field: split
        parts = brand.split()
        if len(parts) >= 2:
            lines.append(f"N:{parts[-1]};{' '.join(parts[:-1])};;;")
        else:
            lines.append(f"N:{brand};;;;")
    if phone:
        # sanitize tel
        tel = re.sub(r"[^+0-9]", "", phone)
        if tel:
            lines.append(f"TEL;TYPE=CELL:{tel}")
    if email and "@" in email:
        lines.append(f"EMAIL;TYPE=INTERNET:{email}")
    if address:
        lines.append(f"ADR;TYPE=WORK:;;{address};;;;")
    # org if available
    org = (site.get("tagline") or "")[:60]
    if org:
        lines.append(f"ORG:{org}")
    url = str(request.base_url).rstrip("/") + f"/api/site/{job_id}"
    lines.append(f"URL:{url}")
    lines.append("END:VCARD")
    vcf = "\r\n".join(lines) + "\r\n"
    from fastapi.responses import Response
    return Response(
        content=vcf.encode("utf-8"),
        media_type="text/vcard; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename=\"{job_id}.vcf\"'},
    )


@app.post("/api/publish/s3/{job_id}")
def publish_s3(job_id: str, request: Request):
    if _limited(request, "publish"):
        return _too_many("publish")
    if not _valid_job_id(job_id):
        return _no_job()
    html = generator.get_site_html(job_id)
    site = generator.get_site_dict(job_id)
    if not html or not site:
        return _no_job()
    # check S3 config via storage
    try:
        try:
            import storage as st  # type: ignore
        except ImportError:
            import sitegen.storage as st  # type: ignore
        bucket = getattr(st, "S3_BUCKET", "") or os.environ.get("SITEGEN_S3_BUCKET", "")
        if not bucket or not st.is_s3():
            return JSONResponse({"error": "S3 не настроен — задайте SITEGEN_S3_BUCKET / SITEGEN_S3_ACCESS_KEY / SITEGEN_S3_SECRET_KEY (см. README / storage.py)"}, status_code=503)
        region = getattr(st, "S3_REGION", "eu-central-1") or os.environ.get("SITEGEN_S3_REGION", "eu-central-1")
        endpoint = getattr(st, "S3_ENDPOINT", "") or os.environ.get("SITEGEN_S3_ENDPOINT", "")
        key = f"sites/{job_id}/index.html"
        # also copy assets if any
        st.save_bytes(key, html.encode())
        # try to save json as well
        try:
            st.save_bytes(f"sites/{job_id}.html", html.encode())
        except Exception:
            pass
        # build public url
        if endpoint:
            base = endpoint.rstrip("/") + f"/{bucket}"
        else:
            base = f"https://{bucket}.s3.{region}.amazonaws.com"
        public_url = f"{base}/{key}"
        # also generate sitemap in S3
        try:
            sitemap = f"""<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{public_url}</loc><lastmod>{time.strftime('%Y-%m-%d')}</lastmod></url></urlset>"""
            st.save_bytes(f"sites/{job_id}/sitemap.xml", sitemap.encode())
        except Exception:
            pass
        return {"ok": True, "url": public_url, "bucket": bucket, "key": key}
    except JSONResponse:
        raise
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"S3 публикация не удалась: {e}"}, status_code=502)


@app.post("/api/publish/static/{job_id}")
def publish_static(job_id: str, request: Request):
    if _limited(request, "publish"):
        return _too_many("publish")
    if not _valid_job_id(job_id):
        return _no_job()
    html = generator.get_site_html(job_id)
    if not html:
        return _no_job()
    # our hosting = just ensure file exists and return our /api/site url
    base = str(request.base_url).rstrip("/")
    public_url = f"{base}/api/site/{job_id}"
    # also ensure S3 mirror if configured (optional)
    try:
        try:
            import storage as st  # type: ignore
        except ImportError:
            import sitegen.storage as st  # type: ignore
        if st.is_s3():
            st.save_bytes(f"sites/{job_id}.html", html.encode())
    except Exception:
        pass
    return {"ok": True, "url": public_url, "hosting": "nelvi"}


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    if not _valid_job_id(job_id):
        return _no_job()
    job = generator.get_job(job_id)
    if not job:
        return _no_job()
    return job


@app.get("/api/site/{job_id}/json")
def site_json(job_id: str):
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    site = generator.get_site_dict(job_id)
    if not site:
        return _no_job()
    return site

@app.get("/api/site/{job_id}", response_class=HTMLResponse)
def site_page(job_id: str):
    if not _valid_job_id(job_id):
        return HTMLResponse("<h1>Сайт не найден</h1>", status_code=404)
    html = generator.get_site_html(job_id)
    if not html:
        return HTMLResponse("<h1>Сайт ещё не готов</h1>", status_code=404)
    return HTMLResponse(html)


# -------------------------------------------------- caddy / sitemap / domain ----
@app.get("/api/caddy/ask")
def caddy_ask(request: Request, domain: str = ""):
    # Caddy on-demand TLS: ?domain=xxx — разрешаем если домен наш или поддомен
    dom = (domain or request.query_params.get("domain") or "").strip().lower().split(":")[0]
    if not dom:
        # Caddy иногда шлёт без параметра — берём host из заголовков
        dom = (request.headers.get("host") or "").split(":")[0].lower()
    if not dom:
        return JSONResponse({"error": "no domain"}, status_code=400)
    if dom in ("localhost", "127.0.0.1", "app"):
        return {"ok": True}
    allowed = (DOMAIN or "").strip().lower()
    if allowed and (dom == allowed or dom.endswith("." + allowed)):
        return {"ok": True}
    if dom.endswith(".nelvi.app") or dom.endswith(".nelvi.local"):
        return {"ok": True}
    # fallback — разрешаем любой поддомен если base_url содержит домен
    return JSONResponse({"error": "not allowed"}, status_code=403)


@app.get("/sitemap.xml")
@app.get("/api/sitemap.xml")
def global_sitemap(request: Request):
    base = str(request.base_url).rstrip("/")
    # собираем id из SITES_DIR
    try:
        ids = [f[:-5] for f in os.listdir(generator.SITES_DIR) if f.endswith(".html") and _valid_job_id(f[:-5])]
    except Exception:
        ids = []
    ids = sorted(ids)[:5000]
    lastmod = time.strftime("%Y-%m-%d")
    urls = "\n".join(f"  <url><loc>{base}/api/site/{jid}</loc><lastmod>{lastmod}</lastmod></url>" for jid in ids[:1000])
    # also include Pages url if DOMAIN
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>"""
    from fastapi.responses import Response
    return Response(content=xml.encode(), media_type="application/xml; charset=utf-8")


class DomainIn(BaseModel):
    domain: str = Field(min_length=1, max_length=253)


@app.post("/api/site/{job_id}/domain")
def set_custom_domain(job_id: str, body: DomainIn, request: Request):
    if not _valid_job_id(job_id):
        return _no_job()
    site = generator.get_site_dict(job_id)
    if not site:
        return _no_job()
    dom = body.domain.strip().lower().rstrip(".")
    # строгая валидация домена: labels 1-63, общий 4..253, без пустых label (\"..\")
    if ".." in dom or dom.startswith(".") or dom.startswith("-") or dom.endswith("-"):
        return JSONResponse({"error": "Некорректный домен (например example.com)"}, status_code=400)
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}", dom):
        return JSONResponse({"error": "Некорректный домен (например example.com)"}, status_code=400)
    if dom.endswith(".local") or dom.startswith("-"):
        return JSONResponse({"error": "Домен недоступен"}, status_code=400)
    site["custom_domain"] = dom
    # сохранить
    html = generator.get_site_html(job_id) or ""
    generator._save_all(job_id, site, html, False)
    return {"ok": True, "domain": dom, "url": f"https://{dom}"}


@app.get("/api/site/{job_id}/p/{slug}", response_class=HTMLResponse)
def site_product_page(job_id: str, slug: str, request: Request):
    if not _valid_job_id(job_id):
        return HTMLResponse("<h1>Сайт не найден</h1>", status_code=404)
    site = generator.get_site_dict(job_id)
    html = generator.get_site_html(job_id)
    if not site or not html:
        return HTMLResponse("<h1>Сайт не найден</h1>", status_code=404)

    def _slug_for(name: str, idx: int = 0) -> str:
        name = (name or "").strip()
        # keep unicode letters/digits for Cyrillic slugs; fallback to item-N
        s = re.sub(r"[^\w]+", "-", name.lower(), flags=re.UNICODE).strip("-")[:60]
        # if slug lost all chars (e.g., pure ascii filtered?) fallback
        if not s or s == "-":
            s = f"item-{idx}" if idx else "item"
        return s

    # ищем по всем секциям с items, где есть name/title (services/prices/products)
    prod = None
    prod_idx = -1
    all_candidates: list[tuple[dict, str]] = []
    for s in (site.get("sections") or []):
        items = s.get("items") or []
        # поддерживаем секции services/prices/products и аналоги
        if s.get("type") in ("products", "services", "prices") or any(isinstance(it, dict) and (it.get("name") or it.get("title")) for it in items):
            for idx, it in enumerate(items):
                if not isinstance(it, dict):
                    continue
                name = (it.get("name") or it.get("title") or "").strip()
                if not name:
                    continue
                cand_slug = it.get("slug") or _slug_for(name, idx)
                all_candidates.append((it, cand_slug))
                if cand_slug == slug or slug == cand_slug.lower():
                    prod = it
                    prod_idx = idx
                    break
        if prod:
            break
    # попытка по частичному совпадению (slug in s_slug) для совместимости
    if not prod:
        for it, cand_slug in all_candidates:
            if slug in cand_slug or cand_slug in slug:
                prod = it
                break
    if not prod and all_candidates:
        # fallback: первый товар/услуга
        prod = all_candidates[0][0]
    if not prod:
        return HTMLResponse("<h1>Товар не найден</h1>", status_code=404)
    # рендерим мини-страницу товара в стиле сайта
    from design import build_css, FONTS_LINK
    theme = site.get("theme") or {}
    accent = theme.get("accent") or "purple"
    mode = theme.get("mode") or "light"
    css = build_css(mode, accent)
    brand = site.get("brand") or "Nelvi"
    title = prod.get("name", "Товар")
    price = prod.get("price", "")
    desc = prod.get("desc", "")
    img_emoji = prod.get("emoji", "🛍️")
    # og
    og_url = str(request.base_url).rstrip("/") + f"/api/site/{job_id}/p/{slug}"
    # try to find image for og
    site_html = html
    page = f"""<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — {brand}</title>
<meta name="description" content="{desc[:160]}">
<meta property="og:title" content="{title} — {brand}">
<meta property="og:description" content="{desc[:160]}">
<meta property="og:url" content="{og_url}">
<meta property="og:type" content="product">
{FONTS_LINK}
<style>{css}</style>
</head><body>
<div class="hdr"><div class="wrap hdr-in"><a class="logo" href="/api/site/{job_id}"><span class="logo-mark" style="width:28px;height:28px;border-radius:8px"><svg viewBox="0 0 24 24" fill="none" width="16" height="16"><path d="M4 12L10 6M4 12L10 18M4 12H20" stroke="white" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="20" cy="12" r="2" fill="white"/></svg></span>{brand}</a><a class="btn ghost" href="/api/site/{job_id}">← На главную</a></div></div>
<div class="wrap section"><div style="max-width:720px;margin:0 auto">
<div style="font-size:64px;text-align:center;margin-bottom:18px">{img_emoji}</div>
<h1 style="text-align:center">{title}</h1>
<p class="lead" style="text-align:center;margin:0 auto 18px">{desc}</p>
<div style="text-align:center;font-family:'Unbounded',sans-serif;font-size:22px;color:var(--accent);margin:18px 0">{price}</div>
<div style="display:flex;gap:12px;justify-content:center"><a class="btn" href="/api/site/{job_id}#catalog">В каталог</a><a class="btn ghost" href="/api/site/{job_id}#contacts">Заказать</a></div>
</div></div>
<footer class="ftr"><div class="wrap ftr-in"><span>© 2026 {brand}</span><span><a href="/api/site/{job_id}">На главную</a></span></div></footer>
</body></html>"""
    return HTMLResponse(page)


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


def _leads_csv(leads: list) -> str:
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["#", "name", "phone", "comment", "type", "items"])
    for i, l in enumerate(leads, 1):
        items = "; ".join(f"{it.get('qty',1)}x{it.get('name','')}" for it in (l.get("items") or []))
        w.writerow([i, l.get("name",""), l.get("phone",""), l.get("comment",""), l.get("type",""), items])
    return buf.getvalue()


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
        # дубль в S3 если включён
        try:
            try:
                import storage as storage  # type: ignore
            except ImportError:
                import sitegen.storage as storage  # type: ignore
            if storage.is_s3():  # type: ignore[attr-defined]
                import json as _j
                storage.save_bytes(f"sites/{site_id}.leads.json", _j.dumps(leads, ensure_ascii=False).encode())  # type: ignore[attr-defined]
        except Exception:
            pass
    tag = "CART" if body.type == "cart" else "LEAD"
    print(f"[{tag}] site={site_id} {body.model_dump()}")
    # Telegram — если задан TELEGRAM_BOT_TOKEN/CHAT_ID
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            import httpx
            items_str = "; ".join(f"{it.get('qty',1)}x{it.get('name','')}" for it in (body.items or [])[:6])
            txt = f"📥 {'Заказ' if body.type=='cart' else 'Заявка'} {site_id}\n👤 {body.name} {body.phone}\n💬 {body.comment[:400]}\n🛒 {items_str[:500]}\n🔗 https://{DOMAIN or 'nelvi.app'}/api/site/{site_id}" if DOMAIN else f"📥 {tag} {site_id}\n👤 {body.name} {body.phone}\n💬 {body.comment[:400]}"
            httpx.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": txt[:4000]}, timeout=6)
        except Exception:
            pass
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


@app.get("/api/leads/{site_id}/csv")
def leads_csv(site_id: str, request: Request):
    if ADMIN_TOKEN:
        got = request.query_params.get("token") or request.headers.get("x-admin-token")
        if got != ADMIN_TOKEN:
            return JSONResponse({"error": "Нужен admin-токен"}, status_code=401)
    if not _valid_job_id(site_id):
        return JSONResponse({"error": "bad site id"}, status_code=400)
    with _LEAD_LOCK:
        data = _read_leads(site_id)
    csv_text = _leads_csv(data)
    from fastapi.responses import Response
    return Response(
        content=csv_text.encode("utf-8-sig"),  # BOM для Excel
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="leads-{site_id}.csv"'},
    )


# ----------------------------------------------------------- авторизация ----

_AUTH_CODES = {}  # email -> {"code","exp","sent","fails"}
_AUTH_LOCK = threading.Lock()
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def _send_code_email(to_email: str, code: str):
    msg = EmailMessage()
    msg["Subject"] = f"Ваш код для Nelvi: {code}"
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

@app.get("/admin", response_class=FileResponse)
def admin():
    return FileResponse(os.path.join(BASE_DIR, "static", "admin.html"))

@app.get("/client", response_class=FileResponse)
def client_panel():
    # тестовая клиентская панель — как видит панель ваш клиент (демо-данные)
    p = os.path.join(BASE_DIR, "static", "client.html")
    if os.path.exists(p):
        return FileResponse(p)
    return FileResponse(os.path.join(BASE_DIR, "static", "admin.html"))

@app.get("/canvas", response_class=FileResponse)
def canvas_editor():
    # Level 3 — свободный визуальный редактор (free canvas, как Tilda/Wix)
    p = os.path.join(BASE_DIR, "static", "canvas.html")
    if os.path.exists(p):
        return FileResponse(p)
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

class CanvasIn(BaseModel):
    blocks: list = Field(default_factory=list)
    bg: str | None = Field(default=None, max_length=20)
    h: int | None = Field(default=None, ge=400, le=4000)
    brand: str | None = Field(default=None, max_length=80)
    theme: dict | None = Field(default=None)

_CANVAS_ALLOWED_TYPES = {"heading","text","button","image","form","divider"}
_CANVAS_MAX_BLOCKS = 80
def _validate_canvas_blocks(blocks):
    if not isinstance(blocks, list):
        return "blocks must be list"
    if len(blocks) > _CANVAS_MAX_BLOCKS:
        return f"too many blocks ({len(blocks)} > {_CANVAS_MAX_BLOCKS})"
    for b in blocks:
        if not isinstance(b, dict):
            return "block must be object"
        t=b.get("type")
        if t not in _CANVAS_ALLOWED_TYPES:
            return f"bad type {t}"
        for k in ("x","y","w","h","z"):
            v=b.get(k)
            if not isinstance(v,(int,float)):
                return f"block {k} must be number"
            if k in ("w","h") and v<1: return f"block {k} too small"
            if v>5000 or v< -5000: return f"block {k} out of bounds"
        props=b.get("props")
        if props is not None and not isinstance(props, dict):
            return "props must be object"
        bid=b.get("id")
        if bid is not None and not isinstance(bid, str):
            return "id must be string"
        if bid and not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", bid):
            return f"bad id {bid}"
    return None


CANVAS_DIR = os.path.join(os.path.dirname(generator.SITES_DIR) if hasattr(generator, "SITES_DIR") else BASE_DIR, "canvas")
try:
    os.makedirs(CANVAS_DIR, exist_ok=True)
except Exception:
    CANVAS_DIR = generator.SITES_DIR

CANVAS_HISTORY_MAX=20
def _canvas_hist_path(job_id): return os.path.join(CANVAS_DIR, f"canvas-{job_id}.history.json")
def _canvas_load_history(job_id):
    hp=_canvas_hist_path(job_id)
    if os.path.exists(hp):
        try:
            with open(hp, encoding="utf-8") as f: d=json.load(f)
            return d if isinstance(d, list) else []
        except: return []
    return []
def _canvas_push_history(job_id, blocks, bg=None, h=None, brand=None, theme=None):
    hist=_canvas_load_history(job_id)
    snap={"ts": int(time.time()), "blocks": blocks}
    if bg: snap["bg"]=bg
    if h: snap["h"]=h
    if brand: snap["brand"]=brand
    if theme: snap["theme"]=theme
    # avoid duplicate consecutive
    import json as _j
    if hist and _j.dumps(hist[-1].get("blocks"), sort_keys=True)==_j.dumps(blocks, sort_keys=True) and hist[-1].get("bg")==bg and hist[-1].get("h")==h:
        return
    hist.append(snap)
    hist=hist[-CANVAS_HISTORY_MAX:]
    try:
        with open(_canvas_hist_path(job_id),"w",encoding="utf-8") as f: _j.dump(hist,f,ensure_ascii=False)
        try:
            try: import storage as st
            except ImportError: import sitegen.storage as st
            if st.is_s3(): st.save_bytes(f"canvas/canvas-{job_id}.history.json", _j.dumps(hist,ensure_ascii=False).encode())
        except: pass
    except: pass

# ---- helpers for canvas html ----
def _canvas_esc(s): return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")
def _canvas_build_html(job_id: str, blocks: list, site_prev: dict|None = None):
    from design import build_css, FONTS_LINK
    site_prev = site_prev or {}
    # theme already resolved above
    # css already built
    # brand/theme from canvas file meta, then site
    try:
        _p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
        if os.path.exists(_p):
            import json as _jj
            with open(_p, encoding="utf-8") as _ff:
                _dd=_jj.load(_ff)
                if isinstance(_dd, dict):
                    if _dd.get("brand"):
                        site_prev=dict(site_prev)
                        site_prev["brand"]=_dd.get("brand")
                    if _dd.get("theme") and isinstance(_dd.get("theme"), dict):
                        site_prev=dict(site_prev)
                        site_prev["theme"]=_dd.get("theme")
    except: pass
    brand = site_prev.get("brand") or "Nelvi Canvas"
    esc=_canvas_esc
    # canvas chrome: bg/h from site or from canvas file meta (stored in site_prev canvas_bg/h or data bg/h)
    canvas_bg = site_prev.get("canvas_bg") or site_prev.get("bg") or "#ffffff"
    canvas_h = site_prev.get("canvas_h") or site_prev.get("h") or 720
    # try to read from canvas file directly if not in site_prev
    try:
        _p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
        if os.path.exists(_p):
            import json as _jj
            with open(_p, encoding="utf-8") as _ff:
                _dd=_jj.load(_ff)
                if isinstance(_dd, dict):
                    if not site_prev.get("canvas_bg") and _dd.get("bg"):
                        canvas_bg=_dd.get("bg")
                    if not site_prev.get("canvas_h") and _dd.get("h"):
                        canvas_h=_dd.get("h")
    except: pass
    # theme for css: from site_prev theme or canvas file theme
    theme = site_prev.get("theme") or {"mode": "light", "accent": "purple"}
    try:
        _p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
        if os.path.exists(_p):
            import json as _jj2
            with open(_p, encoding="utf-8") as _ff2:
                _dd2=_jj2.load(_ff2)
                if isinstance(_dd2, dict) and isinstance(_dd2.get("theme"), dict):
                    theme=_dd2.get("theme")
    except: pass
    accent = theme.get("accent") or "purple"
    mode = theme.get("mode") or "light"
    # validate
    import design as _design
    if mode not in _design.MODES: mode="light"
    if accent not in _design.ACCENTS: accent="purple"
    theme={"mode": mode, "accent": accent}
    from design import build_css, FONTS_LINK
    css = build_css(mode, accent)
    inner=""
    for b in sorted(blocks, key=lambda x: x.get("z",0)):
        x=b.get("x",0); y=b.get("y",0); w=b.get("w",100); h=b.get("h",40); z=b.get("z",1)
        s=f"left:{x}px;top:{y}px;width:{w}px;height:{h}px;z-index:{z};"
        t=b.get("type"); props=b.get("props",{})
        if t=="heading":
            inner+=f'<div style="position:absolute;{s}font-family:Unbounded,sans-serif;font-size:{props.get("size",28)}px;color:{props.get("color","#2B2B36")};font-weight:800">{esc(props.get("text",""))}</div>'
        elif t=="text":
            inner+=f'<div style="position:absolute;{s}font-family:Inter,sans-serif;font-size:{props.get("size",14)}px;color:{props.get("color","#2B2B36")};background:{props.get("bg","transparent")};border:{("1px solid "+props.get("border")) if props.get("border") else "none"};border-radius:10px;padding:10px;white-space:pre-line">{esc(props.get("text",""))}</div>'
        elif t=="button":
            inner+=f'<a href="#" style="position:absolute;{s}display:flex;align-items:center;justify-content:center;background:{props.get("bg","#5B5FEF")};color:{props.get("color","#fff")};border-radius:{props.get("radius",10)}px;font-family:Inter,sans-serif;font-weight:600;text-decoration:none">{esc(props.get("text","Кнопка"))}</a>'
        elif t=="image":
            src=props.get("src","")
            if src:
                inner+=f'<div style="position:absolute;{s}background:{props.get("bg","#EDEFFF")};border-radius:{props.get("radius",12)}px;overflow:hidden"><img src="{src}" style="width:100%;height:100%;object-fit:cover"></div>'
            else:
                inner+=f'<div style="position:absolute;{s}background:{props.get("bg","#EDEFFF")};border-radius:{props.get("radius",12)}px;display:flex;align-items:center;justify-content:center;font-size:42px">{esc(props.get("emoji","🖼️"))}</div>'
        elif t=="form":
            inner+=f'<div style="position:absolute;{s}background:#fff;border:1px solid #E7E5F0;border-radius:12px;padding:14px"><b>{esc(props.get("title","Форма"))}</b><div style="margin-top:8px;display:grid;gap:8px"><input placeholder="Имя" style="padding:10px;border:1px solid #E7E5F0;border-radius:8px"><input placeholder="Телефон" style="padding:10px;border:1px solid #E7E5F0;border-radius:8px"><button style="padding:10px;background:#5B5FEF;color:#fff;border:none;border-radius:8px">Отправить</button></div></div>'
        elif t=="divider":
            inner+=f'<div style="position:absolute;{s}background:{props.get("bg","#E7E5F0")};height:1px"></div>'
    # inject canvas chrome into wrap style
    try: ch=int(canvas_h)
    except: ch=720
    if ch<400: ch=400
    if ch>3000: ch=3000
    bg_safe = canvas_bg if isinstance(canvas_bg, str) and re.fullmatch(r"#([0-9a-fA-F]{3,8})", canvas_bg) else "#ffffff"
    html=f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(brand)} — Nelvi Canvas</title>{FONTS_LINK}<style>{css}</style><style>.wrap{{position:relative;width:1120px;min-height:{ch}px;margin:40px auto;background:{bg_safe};border-radius:16px;box-shadow:0 18px 50px rgba(43,43,54,.12);overflow:hidden}} @media(max-width:1120px){{.wrap{{width:100%;margin:0;border-radius:0}}}}</style></head><body><div class="wrap">{inner}</div></body></html>"""
    site = site_prev or {"brand": brand, "kind": "canvas", "theme": theme, "sections": []}
    site["kind"]="canvas"
    site["theme"]=theme
    site["canvas_blocks"]=blocks
    # preserve canvas chrome
    try:
        if canvas_bg: site["canvas_bg"]=canvas_bg
        if canvas_h: site["canvas_h"]=canvas_h
    except: pass
    return html, site

@app.get("/api/canvases")
def list_canvases():
    # список всех канвасов (id = имя файла без префикса)
    try:
        ids=[]
        for fn in os.listdir(CANVAS_DIR):
            if fn.startswith("canvas-") and fn.endswith(".json"):
                jid=fn[7:-5]
                if _valid_job_id(jid):
                    ids.append(jid)
        # also include demo-canvas if exists in LS but not file? skip
        # sort by mtime desc
        def mtime(j):
            try: return os.path.getmtime(os.path.join(CANVAS_DIR, f"canvas-{j}.json"))
            except: return 0
        ids.sort(key=mtime, reverse=True)
        out=[]
        for jid in ids[:100]:
            p=os.path.join(CANVAS_DIR, f"canvas-{jid}.json")
            try:
                with open(p, encoding="utf-8") as f:
                    data=json.load(f)
                    blocks=data.get("blocks",[]) if isinstance(data, dict) else []
                    bg=data.get("bg") if isinstance(data, dict) else None
                    h=data.get("h") if isinstance(data, dict) else None
                    brand=data.get("brand") if isinstance(data, dict) else None
                    theme=data.get("theme") if isinstance(data, dict) else None
                    out.append({"id": jid, "blocks": len(blocks), "updated": int(mtime(jid)), "bg": bg, "h": h, "brand": brand, "theme": theme})
            except: out.append({"id": jid, "blocks": 0})
        return {"canvases": out}
    except Exception as e:
        return {"canvases": [], "error": str(e)}

@app.post("/api/canvases")
def create_canvas(request: Request):
    # создать новый канвас с рандомным id и пустыми блоками
    if _limited(request, "export"):
        return _too_many("export")
    import uuid
    job_id=uuid.uuid4().hex[:8]
    # ensure unique
    while os.path.exists(os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")):
        job_id=uuid.uuid4().hex[:8]
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    default_blocks=[
        {"id":"h1","type":"heading","x":48,"y":48,"w":520,"h":84,"z":1,"props":{"text":"Сайт за вечер. Без кода.","size":36,"color":"#2B2B36"}},
        {"id":"t1","type":"text","x":48,"y":148,"w":520,"h":72,"z":2,"props":{"text":"Собирай страницы блоками, публикуй в один клик.","size":15,"color":"#7A7A8E"}},
        {"id":"b1","type":"button","x":48,"y":240,"w":180,"h":44,"z":3,"props":{"text":"Попробовать →","bg":"#5B5FEF","color":"#fff","radius":10}},
    ]
    data={"blocks": default_blocks}
    try:
        with open(p,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    base=str(request.base_url).rstrip("/")
    return {"ok": True, "id": job_id, "url": f"{base}/canvas?id={job_id}"}

@app.get("/api/canvas/{job_id}")
def get_canvas(job_id: str):
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    p = os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    if not os.path.exists(p):
        return {"blocks": []}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"blocks": []}

@app.post("/api/canvas/{job_id}")
def save_canvas(job_id: str, body: CanvasIn, request: Request):
    if _limited(request, "export"):
        return _too_many("export")
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    err=_validate_canvas_blocks(body.blocks)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    p = os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    # merge meta: if bg/h/brand/theme not provided, keep existing
    bg = body.bg
    h = body.h
    brand = body.brand
    theme = body.theme
    # if not provided, try to keep old file's meta
    if bg is None or h is None or brand is None or theme is None:
        try:
            if os.path.exists(p):
                with open(p, encoding="utf-8") as _f:
                    _old=json.load(_f)
                    if bg is None: bg=_old.get("bg")
                    if h is None: h=_old.get("h")
                    if brand is None: brand=_old.get("brand")
                    if theme is None: theme=_old.get("theme")
        except: pass
    data = {"blocks": body.blocks}
    if bg: data["bg"]=bg
    if h: data["h"]=h
    if brand: data["brand"]=brand
    if theme: data["theme"]=theme
    # history: save previous blocks if changed
    try:
        _old_blocks=None
        _old_bg=None; _old_h=None; _old_brand=None; _old_theme=None
        if os.path.exists(p):
            import json as _hj
            with open(p, encoding="utf-8") as _hf:
                _od=_hj.load(_hf)
                _old_blocks=_od.get("blocks")
                _old_bg=_od.get("bg")
                _old_h=_od.get("h")
                _old_brand=_od.get("brand")
                _old_theme=_od.get("theme")
        if _old_blocks is not None:
            import json as _j3
            if _j3.dumps(_old_blocks, sort_keys=True)!=_j3.dumps(body.blocks, sort_keys=True) or _old_bg!=bg or _old_h!=h or _old_brand!=brand or _old_theme!=theme:
                _canvas_push_history(job_id, _old_blocks, _old_bg, _old_h, _old_brand, _old_theme)
    except: pass
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        # S3 mirror if configured
        try:
            try: import storage as st
            except ImportError: import sitegen.storage as st
            if st.is_s3():
                st.save_bytes(f"canvas/canvas-{job_id}.json", json.dumps(data, ensure_ascii=False).encode())
        except Exception: pass
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True}

@app.delete("/api/canvas/{job_id}")
def delete_canvas(job_id: str, request: Request):
    if _limited(request, "export"):
        return _too_many("export")
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    hp=_canvas_hist_path(job_id)
    try:
        if os.path.exists(p): os.remove(p)
        if os.path.exists(hp): os.remove(hp)
        # also remove site files if they are canvas kind
        site=generator.get_site_dict(job_id)
        if site and site.get("kind")=="canvas":
            for suf in (".html",".json",".history.json",".chat.json"):
                pp=os.path.join(generator.SITES_DIR, f"{job_id}{suf}")
                try:
                    if os.path.exists(pp): os.remove(pp)
                except: pass
        # S3 delete if possible
        try:
            try: import storage as st
            except ImportError: import sitegen.storage as st
            if st.is_s3():
                # storage may not have delete, just overwrite empty
                try: st.save_bytes(f"canvas/canvas-{job_id}.json", b"{}")
                except: pass
        except: pass
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True}

@app.post("/api/canvas/{job_id}/duplicate")
def duplicate_canvas(job_id: str, request: Request):
    if _limited(request, "export"):
        return _too_many("export")
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    if not os.path.exists(p):
        return _no_job()
    try:
        with open(p, encoding="utf-8") as f: data=json.load(f)
        blocks=data.get("blocks",[]) if isinstance(data, dict) else []
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    import uuid
    new_id=uuid.uuid4().hex[:8]
    while os.path.exists(os.path.join(CANVAS_DIR, f"canvas-{new_id}.json")):
        new_id=uuid.uuid4().hex[:8]
    # shift blocks positions slightly
    import copy
    new_blocks=copy.deepcopy(blocks)
    for b in new_blocks:
        try:
            b["x"]=int(b.get("x",0))+16
            b["y"]=int(b.get("y",0))+16
            # ensure new ids for inner?
        except: pass
    # also copy bg/h/brand/theme meta
    bg=None; h=None; brand=None; theme=None
    try:
        if isinstance(data, dict):
            bg=data.get("bg")
            h=data.get("h")
            brand=data.get("brand")
            theme=data.get("theme")
    except: pass
    np=os.path.join(CANVAS_DIR, f"canvas-{new_id}.json")
    try:
        payload={"blocks": new_blocks}
        if bg: payload["bg"]=bg
        if h: payload["h"]=h
        if brand: payload["brand"]=brand
        if theme: payload["theme"]=theme
        with open(np,"w",encoding="utf-8") as f: json.dump(payload, f, ensure_ascii=False)
        # duplicate site if exists
        site=generator.get_site_dict(job_id)
        if site and site.get("kind")=="canvas":
            html=generator.get_site_html(job_id)
            if html:
                new_site=copy.deepcopy(site)
                # keep brand
                generator._save_all(new_id, new_site, html, False)
        base=str(request.base_url).rstrip("/")
        return {"ok": True, "id": new_id, "url": f"{base}/canvas?id={new_id}"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/canvas/{job_id}/history")
def canvas_history(job_id: str):
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    hist=_canvas_load_history(job_id)
    # return summary without full blocks to keep payload light, but include blocks count
    out=[]
    for i, snap in enumerate(hist):
        out.append({"idx": i, "ts": snap.get("ts"), "blocks": len(snap.get("blocks") or []), "bg": snap.get("bg"), "h": snap.get("h"), "brand": snap.get("brand"), "theme": snap.get("theme")})
    # also include current
    cur=None
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f: cur=json.load(f)
            out.append({"idx": len(hist), "ts": int(time.time()), "blocks": len(cur.get("blocks") or []), "bg": cur.get("bg"), "h": cur.get("h"), "brand": cur.get("brand"), "theme": cur.get("theme"), "current": True})
        except: pass
    return {"history": out, "count": len(hist)}

@app.post("/api/canvas/{job_id}/undo")
def canvas_undo(job_id: str, request: Request):
    if _limited(request, "export"):
        return _too_many("export")
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    hist=_canvas_load_history(job_id)
    if not hist:
        return JSONResponse({"error": "Нечего отменять"}, status_code=400)
    # pop last and restore
    snap=hist.pop()
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    try:
        payload={"blocks": snap.get("blocks") or []}
        if snap.get("bg"): payload["bg"]=snap.get("bg")
        if snap.get("h"): payload["h"]=snap.get("h")
        if snap.get("brand"): payload["brand"]=snap.get("brand")
        if snap.get("theme"): payload["theme"]=snap.get("theme")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        # save back history
        with open(_canvas_hist_path(job_id),"w",encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"ok": True, "restored": snap}


@app.get("/api/canvas/{job_id}/zip")
def canvas_zip(job_id: str, request: Request):
    if _limited(request, "export"):
        return _too_many("export")
    if not _valid_job_id(job_id):
        return _no_job()
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    blocks=[]
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                blocks=json.load(f).get("blocks",[])
        except: blocks=[]
    if not blocks:
        # try fallback to site dict canvas_blocks
        site_prev=generator.get_site_dict(job_id) or {}
        blocks=site_prev.get("canvas_blocks") or []
    if not blocks:
        return JSONResponse({"error": "Канвас пуст"}, status_code=400)
    site_prev=generator.get_site_dict(job_id) or {}
    html, site=_canvas_build_html(job_id, blocks, site_prev)
    import io, zipfile
    brand=(site.get("brand") or job_id).strip()[:40] or job_id
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("index.html", html)
        readme=f"Канвас: {brand}\nЭкспорт Nelvi Canvas — {job_id}\n\nКак залить на хостинг:\n1. Распакуйте архив, загрузите index.html на хостинг.\n2. Сайт — один файл, картинки встроены как data-URI.\n3. Форма шлёт на /api/lead — замените action при необходимости.\n"
        z.writestr("README.txt", readme)
        # also include site json for debug
        try: z.writestr("site.json", json.dumps(site, ensure_ascii=False, indent=2))
        except: pass
        # sitemap for canvas
        try:
            base=str(request.base_url).rstrip("/")
            sitemap=f"""<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{base}/api/site/{job_id}</loc><lastmod>{__import__('time').strftime('%Y-%m-%d')}</lastmod><changefreq>weekly</changefreq><priority>0.9</priority></url></urlset>"""
            z.writestr("sitemap.xml", sitemap)
            z.writestr("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/api/site/{job_id}/sitemap.xml\n")
        except: pass
    buf.seek(0)
    from fastapi.responses import Response
    return Response(content=buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="canvas-{job_id}.zip"'})

@app.post("/api/canvas/{job_id}/publish")
def publish_canvas(job_id: str, request: Request):
    if not _valid_job_id(job_id):
        return JSONResponse({"error": "bad id"}, status_code=400)
    p = os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    blocks=[]
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                blocks = json.load(f).get("blocks", [])
        except Exception:
            blocks=[]
    if not blocks:
        return JSONResponse({"error": "Канвас пуст — добавь блоки"}, status_code=400)
    site_prev = generator.get_site_dict(job_id) or {}
    html, site = _canvas_build_html(job_id, blocks, site_prev)
    generator._save_all(job_id, site, html, False)
    base=str(request.base_url).rstrip("/")
    return {"ok": True, "url": f"{base}/api/site/{job_id}", "html_len": len(html)}

@app.post("/api/canvas/{job_id}/publish/s3")
def publish_canvas_s3(job_id: str, request: Request):
    if _limited(request, "publish"):
        return _too_many("publish")
    if not _valid_job_id(job_id):
        return _no_job()
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    blocks=[]
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f: blocks=json.load(f).get("blocks",[])
        except: blocks=[]
    if not blocks:
        site_prev=generator.get_site_dict(job_id) or {}
        blocks=site_prev.get("canvas_blocks") or []
    if not blocks:
        return JSONResponse({"error": "Канвас пуст"}, status_code=400)
    site_prev=generator.get_site_dict(job_id) or {}
    html, site=_canvas_build_html(job_id, blocks, site_prev)
    # ensure site saved before S3
    generator._save_all(job_id, site, html, False)
    # delegate to S3 logic (same as publish_s3)
    try:
        try: import storage as st
        except ImportError: import sitegen.storage as st
        bucket=getattr(st,"S3_BUCKET","") or os.environ.get("SITEGEN_S3_BUCKET","")
        if not bucket or not st.is_s3():
            return JSONResponse({"error": "S3 не настроен — задайте SITEGEN_S3_BUCKET / SITEGEN_S3_ACCESS_KEY / SITEGEN_S3_SECRET_KEY"}, status_code=503)
        region=getattr(st,"S3_REGION","eu-central-1") or os.environ.get("SITEGEN_S3_REGION","eu-central-1")
        endpoint=getattr(st,"S3_ENDPOINT","") or os.environ.get("SITEGEN_S3_ENDPOINT","")
        key=f"sites/{job_id}/index.html"
        st.save_bytes(key, html.encode())
        try: st.save_bytes(f"sites/{job_id}.html", html.encode())
        except: pass
        if endpoint: base=endpoint.rstrip("/") + f"/{bucket}"
        else: base=f"https://{bucket}.s3.{region}.amazonaws.com"
        public_url=f"{base}/{key}"
        return {"ok": True, "url": public_url, "bucket": bucket, "key": key}
    except JSONResponse:
        raise
    except Exception as e:
        return JSONResponse({"error": f"S3 публикация не удалась: {e}"}, status_code=502)

@app.post("/api/canvas/{job_id}/publish/wp")
def publish_canvas_wp(job_id: str, body: WpPublishIn, request: Request):
    if _limited(request, "publish"):
        return _too_many("publish")
    if not _valid_job_id(job_id):
        return _no_job()
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    blocks=[]
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f: blocks=json.load(f).get("blocks",[])
        except: blocks=[]
    if not blocks:
        site_prev=generator.get_site_dict(job_id) or {}
        blocks=site_prev.get("canvas_blocks") or []
    if not blocks:
        return JSONResponse({"error": "Канвас пуст"}, status_code=400)
    site_prev=generator.get_site_dict(job_id) or {}
    html, site=_canvas_build_html(job_id, blocks, site_prev)
    generator._save_all(job_id, site, html, False)
    # reuse WP logic — same as publish_wp but with canvas html
    try:
        import importer
        wp_base=importer._validate_wp_url(body.wp_url)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    status=body.status.strip().lower()
    if status not in ("draft","publish","private"): status="draft"
    title=(site.get("brand") or "Сайт из Nelvi Canvas")[:120]
    import base64, httpx
    creds=base64.b64encode(f"{body.username}:{body.app_password}".encode()).decode()
    auth_h=f"Basic {creds}"
    wp_base=wp_base.rstrip("/")
    html_for_wp=html
    media_featured_id=None
    try:
        import images as images_mod
        import os as _os
        candidates=[]
        hero_path=_os.path.join(images_mod.ASSETS_DIR, job_id, "hero.webp")
        if _os.path.exists(hero_path): candidates.append(("hero.webp", hero_path))
        prod_dir=_os.path.join(images_mod.ASSETS_DIR, job_id)
        if _os.path.isdir(prod_dir):
            for fn in sorted(_os.listdir(prod_dir)):
                if fn.startswith("prod_") and fn.endswith(".webp"):
                    candidates.append((fn, _os.path.join(prod_dir, fn)))
        for fname, fpath in candidates[:4]:
            try:
                with open(fpath,"rb") as fh: data=fh.read()
                if not data or len(data)>5_000_000: continue
                data_uri=images_mod.data_uri(job_id, fname)
                with httpx.Client(timeout=25.0) as cl:
                    r=cl.post(wp_base+"/wp-json/wp/v2/media", content=data, headers={"Authorization": auth_h, "Content-Disposition": f'attachment; filename="{fname}"', "Content-Type": "image/webp"})
                    r.raise_for_status()
                    j=r.json()
                    media_url=j.get("source_url") or j.get("guid",{}).get("rendered")
                    media_id=j.get("id")
                    if media_url and data_uri and data_uri in html_for_wp:
                        html_for_wp=html_for_wp.replace(data_uri, media_url,1)
                    if fname=="hero.webp" and media_id and not media_featured_id:
                        media_featured_id=media_id
            except Exception as me:
                print(f"[WP-MEDIA-CANVAS] {fname} skipped {me}")
                continue
    except Exception as e:
        print(f"[WP-MEDIA-CANVAS] skip {e}")
    wp_content=f"<!-- wp:html -->\n{html_for_wp}\n<!-- /wp:html -->"
    payload={"title": title, "content": wp_content, "status": status}
    if media_featured_id: payload["featured_media"]=media_featured_id
    headers={"Authorization": auth_h, "Content-Type": "application/json"}
    endpoint=wp_base+"/wp-json/wp/v2/pages"
    try:
        with httpx.Client(timeout=20.0) as client:
            r=client.post(endpoint, json=payload, headers=headers)
            if r.status_code==404:
                endpoint2=wp_base+"/wp-json/wp/v2/posts"
                r=client.post(endpoint2, json=payload, headers=headers)
                endpoint=endpoint2
            r.raise_for_status()
            data=r.json()
            link=data.get("link") or data.get("guid",{}).get("rendered") or wp_base
            out={"ok": True, "url": link, "id": data.get("id"), "endpoint": endpoint}
            if media_featured_id: out["featured_media"]=media_featured_id
            return out
    except httpx.HTTPStatusError as e:
        code=e.response.status_code if e.response is not None else "?"
        detail=""
        try:
            j=e.response.json(); detail=j.get("message") or str(j)[:400]
        except: detail=(e.response.text[:400] if e.response is not None else "")
        return JSONResponse({"error": f"WordPress вернул HTTP {code}: {detail}"}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": f"Не удалось связаться с WordPress: {e}"}, status_code=502)

@app.post("/api/canvas/{job_id}/publish/static")
def publish_canvas_static(job_id: str, request: Request):
    if _limited(request, "publish"):
        return _too_many("publish")
    if not _valid_job_id(job_id):
        return _no_job()
    p=os.path.join(CANVAS_DIR, f"canvas-{job_id}.json")
    blocks=[]
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f: blocks=json.load(f).get("blocks",[])
        except: blocks=[]
    if not blocks:
        site_prev=generator.get_site_dict(job_id) or {}
        blocks=site_prev.get("canvas_blocks") or []
    if not blocks:
        return JSONResponse({"error": "Канвас пуст"}, status_code=400)
    site_prev=generator.get_site_dict(job_id) or {}
    html, site=_canvas_build_html(job_id, blocks, site_prev)
    generator._save_all(job_id, site, html, False)
    try:
        try: import storage as st
        except ImportError: import sitegen.storage as st
        if st.is_s3(): st.save_bytes(f"sites/{job_id}.html", html.encode())
    except: pass
    base=str(request.base_url).rstrip("/")
    public_url=f"{base}/api/site/{job_id}"
    return {"ok": True, "url": public_url, "hosting": "nelvi"}

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


if not ADMIN_TOKEN:
    print("[WARN] SITEGEN_ADMIN_TOKEN не задан — /api/leads открыт всем. "
          "Для публичного стенда задайте токен в .env")
if not auth_enabled():
    print("[INFO] SMTP не настроен — вход по email-коду работает в демо-режиме")
