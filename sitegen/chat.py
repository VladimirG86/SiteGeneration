"""ИИ-редактор сайта: чат → JSON-операции → применение к структуре.

Протокол («агент с инструментами»): модель НЕ перерисовывает сайт саму,
а возвращает список операций (ops), которые детерминированный код применяет
к JSON-структуре. Это даёт:
  — структурные правки (добавить/удалить/переставить секции),
  — дублирующиеся блоки (второй прайс, второй FAQ),
  — превращение лендинга в интернет-магазин (включение корзины + каталог),
  — безопасность: в рендер попадают только провалидированные поля,
  — дешевизну: правится секция, а не весь сайт (поэтому «400 правок/мес»
    у VERSTKA — реальная экономика).

Адресация секций: у каждой секции стабильный `id` («prices», «prices-2»).
Операции принимают `id` (точный блок) или `type` (первый блок этого типа).
Старые сайты без `id` мигрируются автоматически при первой правке.
"""
import copy
import re

# ---------------------------------------------------------------- схемы ----

SECTION_TYPES = ("hero", "services", "advantages", "about", "process",
                 "prices", "reviews", "faq", "contacts", "products",
                 "profile", "tap_links", "socials", "messengers", "qrcode", "vcard", "tap_text")

ACCENTS = ("purple", "blue", "emerald", "orange", "rose", "teal")

# Блоки-одиночки: второй такой же создать нельзя, upsert/add заменяет.
SINGLETON_TYPES = ("hero", "contacts", "profile", "qrcode", "vcard")

# Защита от «наплоди 20 прайсов»: однотипных блоков не больше трёх.
MAX_SAME_TYPE = 3

SECTION_DOC = """- hero: {"type":"hero","title":"H1 до 70 симв","subtitle":"1-2 предложения","cta_primary":"Оставить заявку","cta_secondary":"Смотреть цены","badges":["короткие USP до 30 симв"],"stats":[{"value":"12 лет","label":"на рынке"}]}
- services: {"type":"services","kicker":"Услуги","title":"...","items":[{"name":"услуга","desc":"1 предложение","price":"от 1500 ₽"}]} (3-8 items)
- advantages: {"type":"advantages","kicker":"Почему мы","title":"...","items":[{"title":"2-4 слова","desc":"1 предложение"}]} (3-6)
- about: {"type":"about","kicker":"О компании","title":"...","paragraphs":["2-3 абзаца"],"bullets":["3-5 фактов"]}
- process: {"type":"process","kicker":"Как мы работаем","title":"...","steps":[{"title":"Шаг","desc":"1 предложение"}]} (3-5)
- prices: {"type":"prices","kicker":"Цены","title":"...","note":"пометка или пусто","items":[{"name":"пакет","price":"от 990 ₽","desc":"что входит","includes":["пункты"],"featured":true}]} (2-4)
- reviews: {"type":"reviews","kicker":"Отзывы","title":"...","items":[{"name":"Имя Р.","text":"живой отзыв","meta":"услуга, месяц год"}]} (3-6)
- faq: {"type":"faq","kicker":"FAQ","title":"Частые вопросы","items":[{"q":"вопрос","a":"ответ"}]} (4-6)
- contacts: {"type":"contacts","kicker":"Контакты","title":"...","text":"что будет после заявки","fields":["name","phone","comment"]}
- products (каталог магазина): {"type":"products","kicker":"Каталог","title":"...","items":[{"name":"товар","price":"1 990 ₽ или от 990 ₽","desc":"1 предложение","badge":"Хит/Новинка/-20%/пусто","emoji":"один эмодзи"}]} (4-12)
- profile (taplink/vcard): {"type":"profile","name":"Имя","subtitle":"роль/город","bio":"1-2 предложения","badges":["бейджи до 20 симв"],"avatar_url":"https://... или пусто"}
- tap_links: {"type":"tap_links","kicker":"Ссылки","title":"заголовок","items":[{"title":"Текст кнопки","url":"https://...","subtitle":"пояснение","icon":"эмодзи","style":"filled|outline"}]} (4-12)
- socials: {"type":"socials","kicker":"Соцсети","title":"...","items":[{"platform":"instagram|telegram|whatsapp|youtube|vk|tiktok","url":"https://...","label":"Instagram"}]} (3-10)
- messengers: {"type":"messengers","kicker":"Связаться","title":"...","items":[{"platform":"whatsapp|telegram|viber|phone","url":"https://...","label":"WhatsApp","handle":"+7 ..."}]} (2-6)
- qrcode: {"type":"qrcode","kicker":"QR-код","title":"...","text":"пояснение","data":"строка для QR (url или vcard)","note":"пометка"}
- vcard: {"type":"vcard","kicker":"Контакты","title":"...","items":[{"label":"Телефон","value":"+7...","href":"tel:...","icon":"phone"},{"label":"Email","value":"hi@...","href":"mailto:..."}]} (3-6)
- tap_text: {"type":"tap_text","kicker":"...","title":"...","text":"параграф до 300 симв"}

У каждой секции есть стабильный "id" ("prices", "prices-2"). В upsert_section
передавай "id", чтобы заменить конкретный блок; без "id" заменится первый
блок этого типа. Для ВТОРОГО блока того же типа используй add_section."""

EDITOR_RULES = """Ты — ИИ-редактор сайтов платформы СБОРКА. Клиент описывает изменения словами,
ты возвращаешь JSON со списком операций. Платформа применит их к структуре сайта.

ФОРМАТ ОТВЕДА — ТОЛЬКО JSON без markdown:
{"reply":"короткий ответ клиенту по-русски: что изменил, 1-3 предложения","ops":[...]}

ДОСТУПНЫЕ ОПЕРАЦИИ:
1. {"op":"set_theme","mode":"light","accent":"purple"}  — mode: light|dark; accent: purple|blue|emerald|orange|rose|teal
2. {"op":"set_info","brand":"...","tagline":"...","phone":"+7 (___) ___-__-__","email":"...","address":"..."}  — поля опциональны, меняй только нужные; city не менять
3. {"op":"set_nav","nav":[{"label":"Каталог","href":"#catalog"},{"label":"Услуги","href":"#services"}]}  — 3-6 пунктов на реальные секции
4. {"op":"upsert_section","section":{...}}  — ЗАМЕНИТЬ секцию (по "id", иначе первую такого type) или добавить перед контактами, если такого типа нет
5. {"op":"add_section","section":{...},"after":"services"}  — ВСЕГДА вставить НОВЫЙ блок (для второго блока того же типа); after: id|type|"top", по умолчанию — перед контактами
6. {"op":"delete_section","type":"prices"}  — или {"op":"delete_section","id":"prices-2"} для точного блока
7. {"op":"move_section","type":"prices","after":"services"}  — after: id|type|"top" (в начало)
8. {"op":"set_feature","name":"cart","enabled":true}  — включить/выключить корзину интернет-магазина
9. {"op":"gen_images","target":"hero"} — сгенерировать ИИ-фото на первый экран (~15 c)
10. {"op":"gen_images","target":"products","count":6} — сгенерировать фото для первых 6 товаров каталога (~20-60 c, максимум 8)

ТИПЫ СЕКЦИЙ И ИХ ПОЛЯ:
""" + SECTION_DOC + """

ПРАВИЛА:
1. ПРЕВРАЩЕНИЕ В ИНТЕРНЕТ-МАГАЗИН (главный сценарий): set_feature cart=true +
   upsert_section products (4-12 товаров с ценами и эмодзи) + upsert_section hero
   (cta_primary="Перейти в каталог", title/subtitle под магазин) + set_nav
   (#catalog первым пунктом). О компании/отзывы/контакты оставь — они помогают доверю.
2. НЕ выдумывай телефон/email/адрес, если их нет в текущем сайте или в запросе.
3. Цены — реалистичные для ниши, в рублях: «1 990 ₽», «от 1 500 ₽» или «по запросу».
   Если клиент не дал цен — поставь разумные «от …» и упомяни в reply, что их стоит поправить.
4. Тексты — конкретные, по-человечески. Запрещены клише: «высокое качество»,
   «индивидуальный подход», «команда профессионалов», «широкий ассортимент».
5. Пиши на русском. Обращение к посетителю сайта на «вы».
6. Максимум 8 операций за ответ. Не трогай то, что клиента устраивает.
7. Если запрос уже выполнен в сайте (такая секция есть) — обнови её через upsert, а не дублируй.
   Второй блок того же типа создавай ТОЛЬКО через add_section и только по явной просьбе
   («ещё один», «второй», «другой блок цен»). hero и contacts всегда в единственном числе.
8. Если просьба непонятна — сделай разумное предположение и объясни его в reply.
9. reply — от лица платформы («Готово: добавил каталог…»), без упоминания JSON и операций.
"""

MAX_ITEMS = {"services": 8, "advantages": 6, "about": 5, "process": 5,
             "prices": 4, "reviews": 6, "faq": 7, "products": 12,
             "tap_links": 12, "socials": 10, "messengers": 6, "vcard": 6, "tap_text": 5}


def _s(v, maxlen):
    return str(v or "").strip()[:maxlen]


def _clean_price(p):
    p = _s(p, 24)
    return p if re.search(r"\d|запрос|бесплатн|договор", p, re.I) else ""


def _valid_id(v) -> bool:
    return isinstance(v, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,23}", v) is not None


def sanitize_section(s: dict) -> dict | None:
    """Валидация секции от модели: белый список типов и полей, ограничение длины."""
    if not isinstance(s, dict) or s.get("type") not in SECTION_TYPES:
        return None
    t = s["type"]
    out = {"type": t}
    if _valid_id(s.get("id")):
        out["id"] = s["id"]
    for k in ("kicker", "title", "note", "text"):
        if s.get(k):
            out[k] = _s(s[k], 140)
    if t == "hero":
        for k in ("cta_primary", "cta_secondary"):
            if s.get(k):
                out[k] = _s(s[k], 40)
        out["badges"] = [_s(b, 30) for b in (s.get("badges") or [])[:4] if _s(b, 30)]
        out["stats"] = [{"value": _s(x.get("value"), 20), "label": _s(x.get("label"), 40)}
                        for x in (s.get("stats") or [])[:3] if isinstance(x, dict)]
    if t == "about":
        out["paragraphs"] = [_s(p, 400) for p in (s.get("paragraphs") or [])[:4] if _s(p, 400)]
        out["bullets"] = [_s(b, 90) for b in (s.get("bullets") or [])[:5] if _s(b, 90)]
    if t == "contacts":
        out["fields"] = [f for f in (s.get("fields") or [])[:3] if f in ("name", "phone", "comment")] \
            or ["name", "phone", "comment"]
    items = s.get("items") or []
    if t == "services":
        out["items"] = [{"name": _s(x.get("name"), 60), "desc": _s(x.get("desc"), 200),
                         "price": _clean_price(x.get("price"))}
                        for x in items if isinstance(x, dict) and _s(x.get("name"), 60)][:MAX_ITEMS[t]]
    if t == "advantages":
        out["items"] = [{"title": _s(x.get("title"), 46), "desc": _s(x.get("desc"), 200)}
                        for x in items if isinstance(x, dict) and _s(x.get("title"), 46)][:MAX_ITEMS[t]]
    if t == "process":
        # шаги могут прийти как "steps" (схема генерации и редактор) или
        # "items" (вольность модели) — принимаем оба варианта
        src = s.get("steps") or s.get("items") or []
        out["steps"] = [{"title": _s(x.get("title"), 46), "desc": _s(x.get("desc"), 200)}
                        for x in src if isinstance(x, dict) and _s(x.get("title"), 46)][:MAX_ITEMS[t]]
    if t == "prices":
        out["items"] = [{"name": _s(x.get("name"), 60), "price": _clean_price(x.get("price")) or "по запросу",
                         "desc": _s(x.get("desc"), 200),
                         "includes": [_s(i, 60) for i in (x.get("includes") or [])[:5]],
                         "featured": bool(x.get("featured"))}
                        for x in items if isinstance(x, dict) and _s(x.get("name"), 60)][:MAX_ITEMS[t]]
    if t == "reviews":
        out["items"] = [{"name": _s(x.get("name"), 40), "text": _s(x.get("text"), 300),
                         "meta": _s(x.get("meta"), 60)}
                        for x in items if isinstance(x, dict) and _s(x.get("text"), 300)][:MAX_ITEMS[t]]
    if t == "faq":
        out["items"] = [{"q": _s(x.get("q"), 120), "a": _s(x.get("a"), 400)}
                        for x in items if isinstance(x, dict) and _s(x.get("q"), 120)][:MAX_ITEMS[t]]
    if t == "products":
        out["items"] = [{"name": _s(x.get("name"), 70), "price": _clean_price(x.get("price")) or "по запросу",
                         "desc": _s(x.get("desc"), 200), "badge": _s(x.get("badge"), 16),
                         "emoji": (_s(x.get("emoji"), 4) or "🛍️") if isinstance(x, dict) else "🛍️"}
                        for x in items if isinstance(x, dict) and _s(x.get("name"), 70)][:MAX_ITEMS[t]]
    if t == "profile":
        for k in ("name", "subtitle", "bio", "avatar_url"):
            if s.get(k):
                out[k] = _s(s[k], 140)
        out["badges"] = [_s(b, 20) for b in (s.get("badges") or [])[:4] if _s(b, 20)]
        if not (out.get("name") or out.get("bio")):
            return None
    if t == "tap_links":
        out["items"] = [{"title": _s(x.get("title") or x.get("label"), 60),
                         "url": _s(x.get("url") or x.get("href"), 300) or "#",
                         "subtitle": _s(x.get("subtitle") or x.get("desc"), 80),
                         "icon": _s(x.get("icon"), 4) or "🔗",
                         "style": "filled" if _s(x.get("style"), 10) != "outline" else "outline"}
                        for x in items if isinstance(x, dict) and (_s(x.get("title") or x.get("label"), 60))][:MAX_ITEMS[t]]
        if not out["items"]:
            return None
    if t == "socials":
        out["items"] = [{"platform": _s(x.get("platform") or x.get("label"), 20).lower(),
                         "url": _s(x.get("url"), 300) or "#",
                         "label": _s(x.get("label"), 24) or _s(x.get("platform"), 24)}
                        for x in items if isinstance(x, dict) and _s(x.get("url"), 300)][:MAX_ITEMS[t]]
        if not out["items"]:
            return None
    if t == "messengers":
        out["items"] = [{"platform": _s(x.get("platform"), 20).lower() or "whatsapp",
                         "url": _s(x.get("url"), 300) or "#",
                         "label": _s(x.get("label"), 24) or "Написать",
                         "handle": _s(x.get("handle"), 40)}
                        for x in items if isinstance(x, dict)][:MAX_ITEMS[t]]
        if not out["items"]:
            return None
    if t == "qrcode":
        for k in ("data", "url", "note"):
            if s.get(k):
                out[k] = _s(s[k], 400)
        # data required
        if not (out.get("data") or out.get("url")):
            out["data"] = "https://example.com"
    if t == "vcard":
        out["items"] = [{"label": _s(x.get("label"), 30) or "Контакт",
                         "value": _s(x.get("value") or x.get("text"), 80) or _s(x.get("url"), 80),
                         "href": _s(x.get("href") or x.get("url"), 300),
                         "icon": _s(x.get("icon"), 20) or "phone"}
                        for x in items if isinstance(x, dict)][:MAX_ITEMS[t]]
        if not out["items"]:
            return None
    if t == "tap_text":
        if s.get("text") or s.get("content"):
            out["text"] = _s(s.get("text") or s.get("content"), 600)
        # allow empty? require text
        if not out.get("text"):
            return None
    # секция без обязательного контента — бракуем (иначе рендерер
    # нарисует пустой блок с одним заголовком)
    if t not in ("hero", "contacts", "qrcode", "tap_text"):
        has_content = bool(out.get("items") or out.get("steps")
                           or out.get("paragraphs") or out.get("bullets")
                           or out.get("name") or out.get("bio"))
        if not has_content:
            return None
    return out


def ensure_ids(site: dict) -> dict:
    """Проставляет стабильные id секциям. Существующие корректные id НЕ трогает
    (важно: модель ссылается на них между правками), новым выдаёт свободные.
    Безопасно вызывать на каждом шаге (миграция старых сайтов)."""
    sections = [s for s in site.get("sections", []) or [] if isinstance(s, dict)]
    # проход 1: фиксируем уже занятые id (первое вхождение побеждает при дубле)
    used = set()
    for s in sections:
        cid = s.get("id")
        if _valid_id(cid) and cid not in used:
            used.add(cid)
        else:
            s.pop("id", None)  # дубли и мусор — переназначим ниже
    # проход 2: выдаём id тем, у кого нет
    counters = {}
    for s in sections:
        if s.get("id"):
            continue
        t = s.get("type") or "block"
        counters[t] = counters.get(t, 0) + 1
        cand = t if counters[t] == 1 else f"{t}-{counters[t]}"
        while cand in used:
            counters[t] += 1
            cand = f"{t}-{counters[t]}"
        s["id"] = cand
        used.add(cand)
    return site


def _find(sections: list, ref) -> int | None:
    """Индекс секции по id (точно) или по type (первая). None — не найдена."""
    if not ref:
        return None
    for i, s in enumerate(sections):
        if s.get("id") == ref:
            return i
    for i, s in enumerate(sections):
        if s.get("type") == ref:
            return i
    return None


def _insert_pos(sections: list, after) -> int:
    if after == "top":
        return 0
    if after:
        pos = _find(sections, after)
        if pos is not None:
            return pos + 1
    for i, s in enumerate(sections):
        if s.get("type") == "contacts":
            return i
    return len(sections)


def apply_ops(site: dict, ops: list) -> tuple[int, list]:
    """Применяет операции к структуре. Возвращает (число применённых, список заметок)."""
    applied, notes = 0, []
    ensure_ids(site)
    for op in ops[:8]:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        sections = site.setdefault("sections", [])

        if kind == "set_theme":
            theme = site.setdefault("theme", {})
            if op.get("mode") in ("light", "dark"):
                theme["mode"] = op["mode"]
            if op.get("accent") in ACCENTS:
                theme["accent"] = op["accent"]
            applied += 1

        elif kind == "set_info":
            info = {k: _s(op.get(k), 120) for k in
                    ("brand", "tagline", "phone", "email", "address") if op.get(k)}
            if info:
                site.update(info)
                applied += 1

        elif kind == "set_nav":
            nav = [{"label": _s(n.get("label"), 24), "href": _s(n.get("href"), 40)}
                   for n in (op.get("nav") or [])[:6]
                   if isinstance(n, dict) and _s(n.get("label"), 24)]
            if nav:
                site["nav"] = nav
                applied += 1

        elif kind == "set_feature":
            name = op.get("name")
            if name == "cart":
                site.setdefault("features", {})["cart"] = bool(op.get("enabled", True))
                applied += 1

        elif kind in ("upsert_section", "add_section"):
            sec = sanitize_section(op.get("section"))
            if not sec:
                notes.append("пропущена некорректная секция")
                continue
            if kind == "upsert_section":
                idx = _find(sections, sec["id"]) if sec.get("id") else None
                if idx is None:
                    idx = next((i for i, s in enumerate(sections)
                                if s.get("type") == sec["type"]), None)
                if idx is not None:
                    sec["id"] = sections[idx].get("id")  # id остаётся за позицией
                    sections[idx] = sec
                    applied += 1
                    continue
            # вставка нового блока
            if sec["type"] in SINGLETON_TYPES:
                same = next((i for i, s in enumerate(sections)
                             if s.get("type") == sec["type"]), None)
                if same is not None:
                    sec["id"] = sections[same].get("id")
                    sections[same] = sec
                    notes.append(f"«{sec['type']}» бывает только один — заменил существующий")
                    applied += 1
                    continue
            same_count = sum(1 for s in sections if s.get("type") == sec["type"])
            if same_count >= MAX_SAME_TYPE:
                notes.append(f"блоков «{sec['type']}» уже {MAX_SAME_TYPE} — пропустил")
                continue
            after = op.get("after") if kind == "add_section" else None
            sections.insert(_insert_pos(sections, after), sec)
            ensure_ids(site)
            applied += 1

        elif kind == "delete_section":
            ref = op.get("id") or op.get("type")
            idx = _find(sections, ref)
            if idx is None:
                notes.append(f"секция {ref} не найдена")
            elif len(sections) <= 1:
                notes.append("нельзя удалить последнюю секцию")
            else:
                sections.pop(idx)
                applied += 1

        elif kind == "move_section":
            ref = op.get("id") or op.get("type")
            idx = _find(sections, ref)
            if idx is None:
                notes.append(f"секция {ref} не найдена")
                continue
            sec = sections.pop(idx)
            after = op.get("after")
            if after in ("top", "", None):
                sections.insert(0, sec)
            else:
                pos = _find(sections, after)
                sections.insert((pos + 1) if pos is not None else len(sections), sec)
            applied += 1

    return applied, notes


def build_editor_messages(site: dict, history: list, user_msg: str):
    site_view = copy.deepcopy(site)
    site_view.setdefault("features", {})
    ensure_ids(site_view)  # модель всегда видит актуальные id
    site_json = json_dumps_compact(site_view)
    messages = [{"role": "system", "content": EDITOR_RULES}]
    for m in history[-8:]:
        messages.append({"role": m["role"], "content": m["content"][:1200]})
    messages.append({"role": "user", "content":
                     "ТЕКУЩИЙ САЙТ (JSON):\n" + site_json +
                     "\n\nЗАПРОС КЛИЕНТА: " + user_msg +
                     "\n\nВерни только JSON по формату."})
    return messages


def json_dumps_compact(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def normalize_site(site: dict) -> dict:
    """Приводит сайт, сгенерированный LLM, к безопасной структуре для рендера."""
    if not isinstance(site, dict):
        raise ValueError("сайт не является объектом")
    out = {
        "brand": _s(site.get("brand"), 80) or "Компания",
        "city": _s(site.get("city"), 60),
        "tagline": _s(site.get("tagline"), 60),
        "phone": _s(site.get("phone"), 30),
        "email": _s(site.get("email"), 60),
        "address": _s(site.get("address"), 120),
        "kind": _s(site.get("kind"), 20).lower() if _s(site.get("kind"), 20).lower() in ("landing","taplink","vcard") else "landing",
        "avatar_url": _s(site.get("avatar_url"), 300),
        "avatar_image": bool(site.get("avatar_image")),
        "theme": {
            "mode": (site.get("theme") or {}).get("mode") if isinstance(site.get("theme"), dict) else None,
            "accent": (site.get("theme") or {}).get("accent") if isinstance(site.get("theme"), dict) else None,
        },
        "features": {"cart": bool((site.get("features") or {}).get("cart"))
                     if isinstance(site.get("features"), dict) else False},
    }
    nav = site.get("nav")
    if isinstance(nav, list):
        clean = []
        for n in nav[:6]:
            if isinstance(n, dict) and _s(n.get("label"), 24):
                clean.append({"label": _s(n.get("label"), 24), "href": _s(n.get("href"), 40) or "#"})
            elif isinstance(n, str) and n.strip():
                clean.append({"label": n.strip()[:24], "href": "#"})
        if clean:
            out["nav"] = clean
    sections = site.get("sections")
    if not isinstance(sections, list):
        raise ValueError("sections отсутствуют")
    clean_secs = []
    for s in sections:
        fixed = sanitize_section(s if isinstance(s, dict) else {})
        if fixed:
            clean_secs.append(fixed)
    if not clean_secs:
        raise ValueError("после нормализации не осталось секций")
    out["sections"] = clean_secs
    return ensure_ids(out)
