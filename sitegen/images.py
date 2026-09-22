"""Генерация изображений для сайтов через RouterAI (/api/v1/images).

Этап «Рисуем изображения»:
  — hero: 1 вертикальное фото по смыслу бизнеса (модель по умолчанию —
    bytedance-seed/seedream-4.5, ~4.4 ₽, ~10 c);
  — товары каталога: предметные фото 1:1 (krea-2-medium-turbo, ~1.6 ₽,
    ~20 c), генерируются по запросу в чат-редакторе («сделай фото товаров»).

Все картинки сжимаются (Pillow → webp ~80 КБ) и встраиваются в HTML как
data URI — сайт остаётся самодостаточным файлом. В проде здесь будет S3.
"""
import base64
import io
import os
import threading
import time

import httpx

import llm

BASE_URL = llm.BASE_URL
API_KEY = llm.API_KEY

IMAGE_MODEL = os.environ.get("SITEGEN_IMAGE_MODEL", "bytedance-seed/seedream-4.5")
IMAGE_MODEL_FAST = os.environ.get("SITEGEN_IMAGE_MODEL_FAST", "krea/krea-2-medium-turbo")

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sites", "assets")

# (bytes, cost) cache по файлу — чтобы рендер не читал диск каждый раз
_URI_CACHE = {}
_CACHE_LOCK = threading.Lock()


def is_configured() -> bool:
    return bool(API_KEY)


# ------------------------------------------------------------- генерация ----

def _post_images(payload: dict, timeout: float = 150.0):
    r = httpx.post(f"{BASE_URL}/images",
                   headers={"Authorization": f"Bearer {API_KEY}",
                            "Content-Type": "application/json"},
                   json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    items = data.get("data") or []
    if not items or not items[0].get("b64_json"):
        raise RuntimeError(f"пустой ответ: {str(data)[:150]}")
    cost = (data.get("usage") or {}).get("cost")
    return base64.b64decode(items[0]["b64_json"]), cost


def _postprocess(raw: bytes, max_side: int) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=82, method=6)
    return buf.getvalue()


def generate(prompt: str, model: str = None, aspect: str = "1:1",
             resolution: str = None, max_side: int = 640,
             timeout: float = 150.0):
    """Генерирует изображение, возвращает (webp-байты, стоимость ₽) или None."""
    if not is_configured():
        return None
    payload = {"model": model or IMAGE_MODEL, "prompt": prompt[:1500],
               "n": 1, "aspect_ratio": aspect}
    if resolution:
        payload["resolution"] = resolution
    last_err = None
    for attempt in range(2):
        try:
            raw, cost = _post_images(payload, timeout=timeout)
            return _postprocess(raw, max_side), cost
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5)
    print(f"[IMG] error: {last_err}")
    return None


# ------------------------------------------------------------- промпты ------

HERO_PROMPT_RULES = """Ты арт-директор. Придумай короткий промпт НА АНГЛИЙСКОМ для
генерации вертикального hero-изображения сайта. 1-2 предложения: объект съёмки,
атмосфера, свет, стиль. Фотореалистично, уместно нише, БЕЗ текста и надписей
на изображении, без логотипов. Верни только промпт."""


def hero_prompt(site: dict) -> str:
    about = (site.get("city") and f", {site['city']}" or "")
    desc = ""
    for s in site.get("sections", []):
        if s.get("type") == "hero":
            desc = f"{s.get('title', '')}. {s.get('subtitle', '')}"
            break
    if llm.is_configured():
        try:
            txt = llm.chat(
                [{"role": "system", "content": HERO_PROMPT_RULES},
                 {"role": "user", "content": f"Бизнес: {site.get('brand')} — {desc}{about}"}],
                model=llm.MODEL_FAST, temperature=0.9, max_tokens=300, timeout=60)
            txt = txt.strip().strip('"')
            if 20 < len(txt) < 600:
                return txt + ", professional photography, natural light, no text"
        except Exception:  # noqa: BLE001 — тихо падаем в шаблон
            pass
    return (f"Modern {site.get('niche', 'business')} interior: {desc[:140]}. "
            f"Warm inviting light, professional photography, no text")


def product_prompt(item: dict, site: dict) -> str:
    niche = site.get("niche") or "retail"
    return (f"E-commerce product photo: {item.get('name', 'product')} for {niche} store "
            f"«{site.get('brand', '')}». {item.get('desc', '')[:100]}. "
            f"Clean light studio background, soft shadows, centered composition, no text, no watermark")


# --------------------------------------------------------------- файлы ------

def _asset_path(job_id: str, name: str) -> str:
    d = os.path.join(ASSETS_DIR, job_id)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _save_asset(job_id: str, name: str, data: bytes):
    with open(_asset_path(job_id, name), "wb") as f:
        f.write(data)
    with _CACHE_LOCK:
        _URI_CACHE.pop((job_id, name), None)


def data_uri(job_id: str, name: str):
    """data:image/webp;base64,... из файла ассета (с кэшем), либо None."""
    key = (job_id, name)
    with _CACHE_LOCK:
        if key in _URI_CACHE:
            return _URI_CACHE[key]
    path = _asset_path(job_id, name)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        raw = f.read()
    uri = "data:image/webp;base64," + base64.b64encode(raw).decode()
    with _CACHE_LOCK:
        _URI_CACHE[key] = uri
    return uri


# ------------------------------------------------------- генерация сайта ----

def generate_hero(site: dict, job_id: str) -> bool:
    """Hero-фото для главного экрана. True — получилось."""
    if not is_configured():
        return False
    prompt = hero_prompt(site)
    res = generate(prompt, model=IMAGE_MODEL, aspect="3:4",
                   resolution="2K", max_side=900)
    if not res:
        return False
    img, cost = res
    _save_asset(job_id, "hero.webp", img)
    site["hero_image"] = True
    print(f"[IMG] hero for {job_id}: {len(img)//1024} КБ, {cost} ₽")
    return True


def generate_products(site: dict, job_id: str, count: int = 6, on_progress=None) -> int:
    """Фото для первых count товаров каталога (параллельно). Возвращает сколько.

    on_progress(done, total) вызывается после каждого товара — для прогресса в чате.
    """
    if not is_configured():
        return 0
    items = None
    for s in site.get("sections", []):
        if s.get("type") == "products":
            items = s.get("items") or []
            break
    if not items:
        return 0
    # исходные индексы важны: рендер ищет файл prod_{i}.webp по позиции в каталоге
    targets = [(i, it) for i, it in enumerate(items) if not it.get("image")][:max(0, min(count, 8))]
    done, finished, lock = [0], [0], threading.Lock()

    def report():
        if on_progress:
            with lock:
                d, t = finished[0], len(targets)
            try:
                on_progress(d, t)
            except Exception:  # noqa: BLE001 — прогресс не должен ломать генерацию
                pass

    def work(idx_item):
        idx, it = idx_item
        try:
            res = generate(product_prompt(it, site), model=IMAGE_MODEL_FAST,
                           aspect="1:1", max_side=640)
            if res:
                img, cost = res
                _save_asset(job_id, f"prod_{idx}.webp", img)
                it["image"] = True
                with lock:
                    done[0] += 1
                    print(f"[IMG] prod {idx} for {job_id}: {len(img)//1024} КБ, {cost} ₽")
        finally:
            with lock:
                finished[0] += 1
            report()

    threads = [threading.Thread(target=work, args=(t,)) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=170)
    return done[0]
