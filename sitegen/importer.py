"""Импорт произвольного сайта по URL в модель конструктора.

Пайплайн: URL -> fetch_html -> extract_signals -> LLM(normalize) -> site JSON
                                       └─> heuristic fallback (без LLM)

Защита от SSRF: режем private/loopback/link-local, только http/https,
таймаут 12с, лимит размера 2.5 МБ, редиректы <=3.
"""
import ipaddress
import re
import html as html_lib
import socket
from urllib.parse import urlparse, urljoin

import httpx

# лимит на скачиваемый HTML
MAX_HTML_BYTES = 2_500_000
FETCH_TIMEOUT = 12.0
MAX_REDIRECTS = 3

# ------------------------------------------------------ SSRF guard ----

_PRIVATE_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]
_BLOCKED_HOSTS = {"localhost", "0.0.0.0", "::1"}


def _is_private_ip(host: str) -> bool:
    host = host.strip("[]").lower()
    if host in _BLOCKED_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return any(ip in n for n in _PRIVATE_NETS)
    except ValueError:
        return False


def validate_url(url: str) -> str:
    """Проверка URL импорта/публикации. Возвращает нормализованный URL или бросает ValueError."""
    url = (url or "").strip()
    if not url or len(url) > 2048:
        raise ValueError("Укажите корректный URL (до 2048 символов)")
    # явная схема отличная от http/https — сразу отклоняем (например ftp://)
    if "://" in url and not re.match(r"^https?://", url, re.I):
        raise ValueError("Поддерживаются только http/https")
    # добавляем схему если забыли
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError("Поддерживаются только http/https")
    if not p.hostname:
        raise ValueError("Некорректный адрес сайта")
    host = p.hostname.lower()
    if _is_private_ip(host):
        raise ValueError("Адрес недоступен для импорта")
    # блок .local / .internal
    if host.endswith(".local") or host.endswith(".internal"):
        raise ValueError("Адрес недоступен для импорта")
    # резолвим и проверяем что не резолвится в приватный IP (простая защита)
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in infos:
            ip_str = sockaddr[0]
            if _is_private_ip(ip_str):
                raise ValueError("Адрес резолвится в приватную сеть")
    except socket.gaierror:
        # не удалось резолвить — пусть httpx вернёт ошибку позже, не блокируем
        pass
    # нормализуем (убираем фрагмент)
    return url.split("#")[0].strip()


def _validate_wp_url(url: str) -> str:
    url = validate_url(url)
    # должен быть хотя бы /wp-json намёк не требуем, просто валидный http
    return url.rstrip("/")


# ------------------------------------------------------ fetch ----------

def fetch_html(url: str) -> tuple[str, str]:
    """Скачивает HTML. Возвращает (html, final_url). Бросает RuntimeError."""
    headers = {
        "User-Agent": "SborkaImport/1.0 (+https://sborka.ai)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ru,en;q=0.8",
    }
    try:
        with httpx.Client(
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            headers=headers,
        ) as client:
            r = client.get(url)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if "html" not in ctype.lower() and "text" not in ctype.lower():
                # некоторые отдают text/html без типа — пропускаем, но если точно не html
                if ctype and "json" in ctype.lower():
                    raise RuntimeError(f"URL вернул {ctype}, ожидается HTML-страница")
            data = r.content
            if len(data) > MAX_HTML_BYTES:
                data = data[:MAX_HTML_BYTES]
            # декодируем, уважая charset
            enc = r.encoding or "utf-8"
            try:
                html = data.decode(enc, errors="replace")
            except Exception:
                html = data.decode("utf-8", errors="replace")
            return html, str(r.url)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else "?"
        raise RuntimeError(f"Сайт вернул ошибку HTTP {code}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Не удалось загрузить страницу: {e}")
    except RuntimeError:
        raise
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Ошибка загрузки: {e}")


# ------------------------------------------------------ extract --------

# простые регулярки — без тяжёлых зависимостей (bs4/lxml)
_RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_RE_META_DESC = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]*content=["\'](.*?)["\']', re.I | re.S)
_RE_META_DESC2 = re.compile(
    r'<meta[^>]+content=["\'](.*?)["\'][^>]*name=["\']description["\']', re.I | re.S)
_RE_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_RE_H2 = re.compile(r"<h2[^>]*>(.*?)</h2>", re.I | re.S)
_RE_H3 = re.compile(r"<h3[^>]*>(.*?)</h3>", re.I | re.S)
_RE_P = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)
_RE_A = re.compile(r'<a[^>]+href=["\'](.*?)["\'][^>]*>(.*?)</a>', re.I | re.S)
_RE_IMG = re.compile(r'<img[^>]+src=["\'](.*?)["\']', re.I | re.S)
_RE_PHONE = re.compile(r"(\+7\s*\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2})")
_RE_EMAIL = re.compile(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")
_RE_HEX = re.compile(r"#([0-9a-fA-F]{3,6})\b")
_RE_STRIP_TAGS = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")


def _clean_text(raw: str, limit: int = 500) -> str:
    t = _RE_STRIP_TAGS.sub(" ", raw or "")
    t = html_lib.unescape(t)
    t = _RE_WS.sub(" ", t).strip()
    return t[:limit].strip()


def _extract_list(pattern, html: str, limit=6, clean_limit=140) -> list:
    out = []
    for m in pattern.finditer(html):
        t = _clean_text(m.group(1), clean_limit)
        if len(t) >= 3:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def extract_signals(html: str, base_url: str) -> dict:
    """Вытаскивает сигналы для LLM и эвристики."""
    # title
    mt = _RE_TITLE.search(html)
    title = _clean_text(mt.group(1), 120) if mt else ""
    # description
    md = _RE_META_DESC.search(html) or _RE_META_DESC2.search(html)
    desc = _clean_text(md.group(1), 260) if md else ""
    h1s = _extract_list(_RE_H1, html, 3, 120)
    h2s = _extract_list(_RE_H2, html, 8, 120)
    h3s = _extract_list(_RE_H3, html, 8, 120)
    paras = _extract_list(_RE_P, html, 12, 360)
    # navlinks
    nav = []
    for m in _RE_A.finditer(html):
        href, label = m.group(1).strip(), _clean_text(m.group(2), 40)
        if label and len(label) >= 2 and href and not href.startswith("javascript:"):
            # резолвим относительные
            try:
                href_abs = urljoin(base_url, href)
            except Exception:
                href_abs = href
            nav.append({"label": label, "href": href_abs[:200]})
        if len(nav) >= 12:
            break
    # images (src)
    imgs = []
    for m in _RE_IMG.finditer(html):
        src = m.group(1).strip()
        if src and not src.startswith("data:"):
            try:
                src_abs = urljoin(base_url, src)
            except Exception:
                src_abs = src
            imgs.append(src_abs[:500])
        if len(imgs) >= 8:
            break
    # contacts
    phones = _RE_PHONE.findall(html)[:3]
    emails = [e for e in _RE_EMAIL.findall(html) if "example" not in e.lower()][:3]
    # colors
    hex_colors = []
    for m in _RE_HEX.finditer(html):
        c = "#" + m.group(1).lower()
        if len(c) in (4, 7) and c not in hex_colors:
            hex_colors.append(c)
        if len(hex_colors) >= 10:
            break
    # full text dump for LLM (обрезанный, без скриптов/стилей)
    text_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text_html = re.sub(r"<[^>]+>", " ", text_html)
    text_html = html_lib.unescape(text_html)
    text_html = _RE_WS.sub(" ", text_html).strip()
    # ограничиваем до ~8000 символов
    text_dump = text_html[:8000]

    return {
        "url": base_url,
        "title": title,
        "description": desc,
        "h1": h1s,
        "h2": h2s,
        "h3": h3s,
        "paragraphs": paras,
        "nav": nav,
        "images": imgs,
        "phones": phones,
        "emails": emails,
        "colors": hex_colors,
        "text_dump": text_dump,
    }


# ------------------------------------------------------ LLM normalize ---

# --- автопалитра: мапим найденные hex на ближайший акцент ---
_ACCENT_RGB = {
    "purple": (124, 58, 237),
    "blue": (37, 99, 235),
    "emerald": (5, 150, 105),
    "orange": (234, 88, 12),
    "rose": (225, 29, 72),
    "teal": (13, 148, 136),
}


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return None


def pick_accent_from_colors(hex_colors: list) -> str | None:
    """Находит акцент, ближайший к доминирующим цветам оригинала."""
    if not hex_colors:
        return None
    best, best_dist = None, 1e9
    for hex_c in hex_colors[:6]:
        rgb = _hex_to_rgb(hex_c)
        if not rgb:
            continue
        # игнорируем слишком светлые/тёмные/серые (низкая насыщенность)
        r, g, b = rgb
        mx, mn = max(rgb), min(rgb)
        if mx < 40 or mx > 245 and mn > 220:  # почти чёрный/белый
            continue
        if mx - mn < 18:  # серый
            continue
        for name, ar in _ACCENT_RGB.items():
            d = (r - ar[0]) ** 2 + (g - ar[1]) ** 2 + (b - ar[2]) ** 2
            if d < best_dist:
                best_dist, best = d, name
    # только если достаточно близко (иначе оставляем дефолт)
    if best is not None and best_dist < 14000:  # ~118 per channel
        return best
    return None


def _download_image_bytes(url: str, timeout: float = 9.0, max_bytes: int = 4_500_000) -> bytes | None:
    try:
        # SSRF-проверка для картинок (те же правила)
        validate_url(url)
    except ValueError:
        return None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, max_redirects=3,
                          headers={"User-Agent": "SborkaImport/1.0"}) as cl:
            r = cl.get(url)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            if ctype and "image" not in ctype.lower():
                return None
            data = r.content
            if not data or len(data) > max_bytes:
                return None
            return data
    except Exception:
        return None


def _to_webp(data: bytes, max_side: int = 900) -> bytes | None:
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data)).convert("RGB")
        # учитываем EXIF повороты
        try:
            from PIL import ImageOps
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "WEBP", quality=82, method=6)
        out = buf.getvalue()
        if len(out) > 900_000:
            # пережать сильнее если велико
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=76, method=6)
            out = buf.getvalue()
        return out
    except Exception:
        return None


def try_attach_original_images(site: dict, signals: dict, job_id: str) -> bool:
    """Пытается скачать первое фото оригинала и поставить как hero. True если удалось."""
    imgs = [u for u in (signals.get("images") or []) if u and isinstance(u, str)]
    if not imgs:
        return False
    # берём первые 3 — часто первое — лого, поэтому пробуем по очереди
    for img_url in imgs[:3]:
        data = _download_image_bytes(img_url)
        if not data:
            continue
        webp = _to_webp(data, max_side=900)
        if not webp or len(webp) < 5000:  # слишком мало — возможно трекер-пиксель
            continue
        try:
            from images import _save_asset
            _save_asset(job_id, "hero.webp", webp)
            site["hero_image"] = True
            return True
        except Exception:
            continue
    return False


def heuristic_site(signals: dict, theme_mode: str = "light", accent: str = "purple") -> dict:
    """Детерминированный фолбэк без LLM: собирает минимальный сайт из сигналов."""
    # автопалитра: если дефолт — попробуем ближайший к оригиналу
    if accent == "purple":
        picked = pick_accent_from_colors(signals.get("colors") or [])
        if picked:
            accent = picked
    title = signals.get("title") or (signals.get("h1") or ["Компания"])[0]
    brand = title[:80].strip() or "Компания"
    desc = signals.get("description") or " ".join(signals.get("paragraphs") or [])[:160] or f"{brand} — услуги для клиентов"
    h1 = (signals.get("h1") or [f"{brand} — услуги в вашем городе"])[0][:70]
    phones = signals.get("phones") or []
    emails = signals.get("emails") or []
    paras = signals.get("paragraphs") or []
    h2s = signals.get("h2") or []
    h3s = signals.get("h3") or []
    text_dump = signals.get("text_dump") or " ".join(paras + h2s + h3s).lower()

    # эвристика магазина vs услуги: цены, каталог, корзина, купить
    def _looks_like_shop() -> bool:
        t = text_dump.lower()
        price_hits = len(re.findall(r"\d[\d\s]*\s*₽|\d+\s*руб|\$\s*\d|€\s*\d", t))
        shop_words = sum(t.count(w) for w in ["каталог", "товар", "купить", "корзин", "доставк", "цен", "магазин"])
        return price_hits >= 3 or shop_words >= 5

    is_shop = _looks_like_shop()

    # hero
    hero = {
        "type": "hero",
        "title": h1,
        "subtitle": desc[:160],
        "cta_primary": "Оставить заявку",
        "cta_secondary": "Подробнее",
        "badges": [p[:24] for p in h3s[:3]] or ["Работаем для вас"],
        "stats": [],
    }
    # services from h2/h3
    svc_items = []
    for t in (h2s + h3s)[:8]:
        svc_items.append({"name": t[:60], "desc": (paras[len(svc_items)] if len(svc_items) < len(paras) else t)[:180], "price": "по запросу"})
    if not svc_items:
        svc_items = [{"name": "Основная услуга", "desc": desc[:180] or "Подробнее по телефону", "price": "по запросу"}]
    services = {"type": "services", "kicker": "Услуги", "title": "Что мы делаем", "items": svc_items[:6]}
    advantages = {
        "type": "advantages", "kicker": "Почему мы", "title": "Наши преимущества",
        "items": [{"title": h[:30] or f"Преимущество {i+1}", "desc": (paras[i] if i < len(paras) else h)[:180]}
                  for i, h in enumerate((h2s[:3] or ["Опыт", "Качество", "Скорость"]))][:3]
    }
    about = {
        "type": "about", "kicker": "О компании", "title": f"О компании {brand}",
        "paragraphs": paras[:3] or [desc], "bullets": h3s[:4] or ["Работаем по договору", "Гарантия на услуги"]
    }
    contacts = {
        "type": "contacts", "kicker": "Контакты", "title": "Оставьте заявку",
        "text": "Перезвоним в течение рабочего дня.", "fields": ["name", "phone", "comment"]
    }
    # если похоже на магазин — делаем каталог с ценами и корзиной
    if is_shop:
        # вытаскиваем цены из текста
        price_pat = re.compile(r"(\d[\d\s]*\s*₽|от\s*\d[\d\s]*\s*₽|\d[\d\s]*\s*руб\.?|\$\s*\d+)", re.I)
        prod_items = []
        candidates = (h2s + h3s + paras)[:12]
        for cand in candidates:
            # ищем цену в самой строке
            m = price_pat.search(cand)
            price = m.group(1).strip()[:24] if m else "по запросу"
            # имя — чистим от цены
            name = price_pat.sub("", cand).strip()[:60] or cand[:60]
            if len(name) < 3 or name.lower() in ("каталог", "товары", "продукция"):
                continue
            # desc — следующий абзац или обрезанный cand
            desc_prod = next((p for p in paras if p != cand and name[:10].lower() not in p.lower()), cand)[:140]
            prod_items.append({"name": name, "price": price, "desc": desc_prod, "badge": "", "emoji": "🛍️"})
            if len(prod_items) >= 6:
                break
        if len(prod_items) >= 3:
            products = {"type": "products", "kicker": "Каталог", "title": "Каталог товаров", "items": prod_items[:8]}
            # вставляем после services
            sections = [hero, services, products, advantages, about, contacts]
            hero["cta_primary"] = "Перейти в каталог"
            site = {
                "brand": brand,
                "city": "",
                "tagline": desc[:40],
                "phone": phones[0] if phones else "",
                "email": emails[0] if emails else "",
                "address": "",
                "theme": {"mode": theme_mode, "accent": accent},
                "nav": [{"label": "Каталог", "href": "#catalog"}, {"label": "О нас", "href": "#about"}, {"label": "Контакты", "href": "#contacts"}],
                "sections": sections,
                "features": {"cart": True},
                "import_source": signals.get("url", ""),
            }
            return site

    site = {
        "brand": brand,
        "city": "",
        "tagline": desc[:40],
        "phone": phones[0] if phones else "",
        "email": emails[0] if emails else "",
        "address": "",
        "theme": {"mode": theme_mode, "accent": accent},
        "nav": [{"label": "Услуги", "href": "#services"}, {"label": "О нас", "href": "#about"}, {"label": "Контакты", "href": "#contacts"}],
        "sections": [hero, services, advantages, about, contacts],
        "features": {"cart": False},
        "import_source": signals.get("url", ""),
    }
    return site


def build_llm_site(signals: dict, theme_mode: str = "light", accent: str = "purple") -> dict:
    """Пытается через LLM, иначе — эвристика. Возвращает нормализованный site."""
    import llm
    import chat as chat_ops
    import design

    # автопалитра до выбора модели (LLM увидит правильный акцент)
    if accent == "purple":
        picked = pick_accent_from_colors(signals.get("colors") or [])
        if picked:
            accent = picked

    if not llm.is_configured():
        site = heuristic_site(signals, theme_mode, accent)
        return chat_ops.normalize_site(site)

    # собираем промпт
    import prompts
    # ограниченный дайджест сигналов
    digest = {
        "url": signals.get("url"),
        "title": signals.get("title"),
        "description": signals.get("description"),
        "h1": signals.get("h1"),
        "h2": signals.get("h2"),
        "paragraphs": signals.get("paragraphs")[:8],
        "phones": signals.get("phones"),
        "emails": signals.get("emails"),
        "colors": signals.get("colors")[:6],
        "text_excerpt": signals.get("text_dump", "")[:5000],
    }
    acc = design.ACCENTS.get(accent) or design.ACCENTS["purple"]
    messages = prompts.build_import_messages(digest, theme_mode, acc["label"], acc["main"])
    raw = llm.chat(messages, temperature=0.35, max_tokens=16000, timeout=120)
    site = llm.extract_json(raw)
    # помечаем источник
    site["import_source"] = signals.get("url", "")
    site = chat_ops.normalize_site(site)
    # форсируем тему импорта
    site["theme"] = {"mode": theme_mode, "accent": accent}
    if not site.get("brand"):
        site["brand"] = signals.get("title") or "Компания"
    return site
