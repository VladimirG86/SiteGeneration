"""Прототип ИИ-конструктора сайтов (аналог VERSTKA.ai) — API-сервер.

Запуск:
  uvicorn app:app --host 0.0.0.0 --port 8000

Ключ RouterAI читается из .env (или переменных окружения) — см. llm.py.
Без ключа работает демо-режим (demo_content.py).
"""
import os
import threading

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import design
import generator
import llm
import niches

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="SiteGen prototype")

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


# ------------------------------------------------------------------- api ----

@app.get("/api/config")
def config():
    import images
    return {
        "llm": llm.is_configured(),
        "model": llm.MODEL if llm.is_configured() else None,
        "editor": llm.is_configured(),
        "images": images.is_configured(),
        "accents": [{"id": k, "label": v["label"], "hex": v["main"]} for k, v in design.ACCENTS.items()],
        "modes": list(design.MODES),
    }


@app.post("/api/analyze")
def analyze(body: AnalyzeIn):
    """После шага «О бизнесе»: определяем нишу и отдаём подсказки-чипы."""
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
def generate(body: GenerateIn):
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


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    job = generator.get_job(job_id)
    if not job:
        return JSONResponse({"error": "job not found"}, status_code=404)
    return job


@app.get("/api/site/{job_id}", response_class=HTMLResponse)
def site_page(job_id: str):
    html = generator.get_site_html(job_id)
    if not html:
        return HTMLResponse("<h1>Сайт ещё не готов</h1>", status_code=404)
    return HTMLResponse(html)


# -------------------------------------------------------------- редактор ----

@app.post("/api/chat/{job_id}")
def chat_edit(job_id: str, body: ChatIn):
    if not llm.is_configured():
        return JSONResponse({"error": "Редактору нужен ключ RouterAI (.env)"}, status_code=503)
    try:
        result = generator.edit_site(job_id, body.message)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"Ошибка ИИ-правки: {e}"}, status_code=502)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return result


@app.post("/api/undo/{job_id}")
def undo_edit(job_id: str):
    result = generator.undo(job_id)
    if "error" in result:
        return JSONResponse(result, status_code=400)
    return result


# --------------------------------------------------------------- заявки -----

_LEADS = {}
_LEAD_LOCK = threading.Lock()


@app.post("/api/lead/{site_id}")
def lead(site_id: str, body: LeadIn):
    with _LEAD_LOCK:
        _LEADS.setdefault(site_id, []).append(body.model_dump())
    tag = "CART" if body.type == "cart" else "LEAD"
    print(f"[{tag}] site={site_id} {body.model_dump()}")
    return {"ok": True}


@app.get("/api/leads/{site_id}")
def leads(site_id: str):
    with _LEAD_LOCK:
        return _LEADS.get(site_id, [])


# --------------------------------------------------------------- static ----

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))
