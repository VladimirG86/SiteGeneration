"""Демо-генератор контента: собирает сайт по анкете без LLM.

Нужен, чтобы прототип полностью работал без API-ключа (и как фолбэк,
если RouterAI недоступен). В боевом режиме контент отдаёт модель по prompts.py.
"""
import re

import niches

# «в Москве» (как в тексте) -> «Москва» (именительный, для подписей)
CITY_NOM = {"Москве": "Москва", "Санкт-Петербурге": "Санкт-Петербург",
            "Казани": "Казань", "Екатеринбурге": "Екатеринбург",
            "Новосибирске": "Новосибирск", "Раменском": "Раменское",
            "Сочи": "Сочи", "Челябинске": "Челябинск", "Краснодаре": "Краснодар",
            "Нижнем Новгороде": "Нижний Новгород", "Самаре": "Самара",
            "Ростове-на-Дону": "Ростов-на-Дону", "Уфе": "Уфа",
            "Твери": "Тверь", "Владивостоке": "Владивосток",
            "Перми": "Пермь", "Тюмени": "Тюмень", "Омске": "Омск"}

PRICE_RE = re.compile(r"\s*[-—–=]\s*|\s+по\s+(\d|\d[\d\s]{1,7})\s*(₽|руб)", re.I)
TAIL_PRICE_RE = re.compile(
    r"\s*[-—–]\s*(от|до)?\s*(\d[\d\s]{1,7})\s*(₽|руб|р\.|тыс)?", re.I)


def extract_city(text: str):
    """Возвращает (именительный, фраза_с_предлогом): («Москва», «в Москве»)."""
    t = text or ""
    for prep, nom in CITY_NOM.items():
        if prep in t or nom in t:
            if prep in t:
                return nom, f"в {prep}"
            # нашли именительный — склоняем по словарю в обратную сторону
            for p2, n2 in CITY_NOM.items():
                if n2 == nom:
                    return nom, f"в {p2}"
            return nom, f"в {nom}"
    m = re.search(r"\b(?:в|г\.\s?|городе?\s+)\s*([А-ЯЁ][а-яё\-]{2,})", t)
    if m:
        return m.group(1), f"в {m.group(1)}"
    return "", ""


def _clean_name_price(line: str):
    """«Диагностика - от 1500 руб» → («Диагностика», «от 1500 ₽»)."""
    m = TAIL_PRICE_RE.search(line)
    if not m:
        m2 = re.search(r"\s*[-—–]\s*(бесплатно|по запросу|договорная|по прайсу)\s*$", line, re.I)
        if m2:
            return line[:m2.start()].strip(" .-–—"), m2.group(1).lower()
        return line.strip(" .-–—"), ""
    name = line[:m.start()].strip(" .-–—")
    price = ((m.group(1) + " ") if m.group(1) else "") + \
        f"{int(m.group(2).replace(' ', '')):,}".replace(",", " ") + " ₽"
    return name, price


def _split_products(text: str):
    out = []
    for raw in re.split(r"[\n;]+", text or ""):
        raw = raw.strip(" .-–—")
        if not (2 < len(raw) <= 90):
            continue
        name, price = _clean_name_price(raw)
        if len(name) > 3:
            out.append({"name": name, "price": price})
    return out[:8]


def _split_advantages(text: str):
    out = []
    for raw in re.split(r"[\n;]+|,\s*", text or ""):
        raw = raw.strip(" .-–—")
        if 3 < len(raw) <= 70:
            out.append(raw)
    return out[:6]


ADV_DESC = [
    ("гарант", "Фиксируем в договоре и действительно исполняем."),
    ("выезд", "Приезжаем в день обращения, без ожидания неделю."),
    ("опыт|лет", "За плечами — сотни выполненных заказов."),
    ("цен|смет|стоим|дешев|₽", "Смета до начала работ, без «доплатите ещё»."),
    ("договор", "Работаем официально, документы для физлиц и компаний."),
    ("запчаст|оригин", "Подбираем варианты под бюджет, согласуем заранее."),
    ("скор|день|минут|час|быстр", "Не заставляем ждать — отвечаем сразу."),
]


def _adv_item(text: str, i: int):
    title = text[0].upper() + text[1:]
    title = title if len(title) <= 46 else title[:44].rstrip(" ,.") + "…"
    desc = "Проверено на реальных заказах — спросите наших клиентов."
    for pat, d in ADV_DESC:
        if re.search(pat, text.lower()):
            desc = d
            break
    return {"title": title, "desc": desc}


def _price_from(text: str):
    m = TAIL_PRICE_RE.search(text or "")
    if m:
        num = int(m.group(2).replace(" ", ""))
        return f"{(m.group(1) + ' ') if m.group(1) else ''}{num:,} ₽".replace(",", " ")
    return ""


def build_site(answers: dict, theme_mode: str, accent: str) -> dict:
    a = lambda key: answers.get(key) or answers.get(
        {"Название": "name", "О бизнесе": "about", "Услуги/товары": "products",
         "Преимущества": "advantages", "Дополнительно": "extras"}[key]) or ""
    name = a("Название").strip() or "Наша компания"
    about_text = a("О бизнесе").strip()
    prod_lines = _split_products(a("Услуги/товары"))
    advantages = _split_advantages(a("Преимущества"))
    extras = [x.strip(" .-–—") for x in re.split(r"[\n;]+|,\s*", a("Дополнительно")) if 3 < len(x.strip()) <= 70][:5]

    city_nom, city_in = extract_city(about_text + " " + name)
    niche = niches.detect_niche(about_text + " " + " ".join(p["name"] for p in prod_lines))
    bank = niches.chips_for(niche)

    # ---------- hero ----------
    first = prod_lines[0]["name"] if prod_lines else bank["products"][0].lower()
    first_short = first if len(first) <= 42 else first[:40].rstrip(" .") + "…"
    hero_title = f"{first_short[0].upper() + first_short[1:]} {city_in} — быстро и с гарантией".replace("  ", " ") \
        if city_in else f"{first_short[0].upper() + first_short[1:]} — быстро и с гарантией"
    about_short = about_text.rstrip(". ")
    if 25 < len(about_short) <= 170 and about_short.lower()[:12] != name.lower()[:12]:
        hero_sub = f"{name} — {about_short}. Работаем по договору, стоимость фиксируем до начала работ."
    elif about_short:
        hero_sub = f"{about_short}. Работаем по договору, стоимость фиксируем до начала работ."
    else:
        hero_sub = f"{name}: работаем по договору, стоимость фиксируем до начала работ."
    hero_stats = [{"value": "15 мин", "label": "отвечаем на заявку"},
                  {"value": "1 год", "label": "гарантия по договору"},
                  {"value": "0 ₽", "label": "диагностика перед работой"}]

    # ---------- services ----------
    services_items = []
    for p in (prod_lines or [{"name": n, "price": ""} for n in bank["products"][:6]]):
        services_items.append({
            "name": p["name"],
            "desc": f"{p['name']}: с предварительной диагностикой и честной сметой.",
            "price": p.get("price") or _price_from(a("Услуги/товары")),
        })

    # ---------- advantages ----------
    adv_src = advantages or bank["advantages"]
    adv_items = [_adv_item(x, i) for i, x in enumerate(adv_src[:6])]

    # ---------- about ----------
    p1 = f"«{name}»" + (f" работает {city_in}." if city_in else ".")
    if 25 < len(about_short) <= 220 and about_short.lower()[:12] != name.lower()[:12]:
        p1 += f" {about_short[0].upper() + about_short[1:]}."
    else:
        p1 += " Небольшая команда специалистов, которая отвечает за результат головой, а не обещаниями."
    about_paras = [
        p1,
        "Не берём заказ, если не уверены в результате: сначала диагностика и точная смета, "
        "потом работа. Цена после сметы не меняется.",
    ]
    about_bullets = extras or bank["extras"][:5]

    # ---------- process ----------
    steps = [
        {"title": "Заявка", "desc": "Оставляете заявку на сайте или звоните — отвечаем в течение 15 минут."},
        {"title": "Смета", "desc": "Смотрим задачу, называем точную стоимость и сроки до начала работ."},
        {"title": "Работа", "desc": "Выполняем по договору и держим вас в курсе на каждом этапе."},
        {"title": "Приёмка", "desc": "Показываем результат и подписываем акт — вступает в силу гарантия."},
    ]

    # ---------- prices ----------
    price_items = []
    for i, s in enumerate(services_items[:3]):
        price_items.append({
            "name": s["name"],
            "price": s["price"] or "по запросу",
            "desc": "Включает диагностику, материалы и гарантийное обслуживание после сдачи.",
            "includes": ["Диагностика бесплатно", "Смета до начала работ", "Гарантия по договору"],
            "featured": i == 1,
        })
    note = "Цены ориентировочные — точная смета после диагностики, до начала работ."

    # ---------- reviews ----------
    first_service = services_items[0]["name"] if services_items else "Заказ"
    reviews_items = [
        {"name": "Мария Р.", "meta": f"{first_service}, июль 2026",
         "text": f"Обратились в «{name}» по рекомендации. Смету дали до начала работ, "
                 "сделали в срок, цена не изменилась ни на рубль."},
        {"name": "Олег Л.", "meta": "Повторный заказ, март 2026",
         "text": "Понравилось, что держали в курсе каждый этап и присылали фото. "
                 "Вопросы решали сразу, без «завтра сделаем»."},
        {"name": "Елена К.", "meta": "Срочный заказ, август 2026",
         "text": "Сначала сомневалась, но договор и фиксированная смета всё прояснили. "
                 "Результатом довольна, буду обращаться ещё."},
    ]

    # ---------- faq ----------
    faq_items = [
        {"q": "Сколько стоит и от чего зависит цена?",
         "a": "Стоимость зависит от объёма работ. После диагностики называем точную сумму "
              "и фиксируем её в договоре — «доплатите ещё» не будет."},
        {"q": "Какие гарантии вы даёте?",
         "a": "Гарантия до 1 года на все работы фиксируется в договоре. "
              "Если что-то пойдёт не так — исправим бесплатно."},
        {"q": "Как быстро вы начинаете работу?",
         "a": "Обычно берём заказ в день обращения"
              + (f" {city_in}" if city_in else "") + ". Срочные заказы обсуждаются индивидуально."},
        {"q": "Как оплатить?",
         "a": "Оплата по этапам: картой, переводом или наличными. "
              "Предоплату просим только на материалы."},
    ]

    return {
        "brand": name,
        "city": city_nom,
        "niche": niche,
        "tagline": adv_src[0][:38].rstrip(" .") if adv_src else "Работаем по договору",
        "phone": "+7 (900) 123-45-67",
        "email": "",
        "address": (f"{city_nom}, работаем по городу и области" if city_nom else ""),
        "nav": [{"label": "Услуги", "href": "#services"},
                {"label": "Цены", "href": "#prices"},
                {"label": "О нас", "href": "#about"},
                {"label": "Вопросы", "href": "#faq"},
                {"label": "Контакты", "href": "#contacts"}],
        "sections": [
            {"type": "hero", "title": hero_title, "subtitle": hero_sub,
             "cta_primary": "Оставить заявку", "cta_secondary": "Смотреть цены",
             "badges": [x if len(x) <= 30 else x[:28].rstrip(" ,.") + "…" for x in adv_src[:3]],
             "stats": hero_stats},
            {"type": "services", "kicker": "Услуги", "title": "Чем мы можем помочь",
             "items": services_items},
            {"type": "advantages", "kicker": "Почему мы", "title": "Выбирают нас — и вот почему",
             "items": adv_items},
            {"type": "about", "kicker": "О компании", "title": f"Немного о «{name}»",
             "paragraphs": about_paras, "bullets": about_bullets},
            {"type": "process", "kicker": "Как мы работаем", "title": "От заявки до результата — 4 шага",
             "steps": steps},
            {"type": "prices", "kicker": "Цены", "title": "Честные цены",
             "note": note, "items": price_items},
            {"type": "reviews", "kicker": "Отзывы", "title": "Что говорят клиенты",
             "items": reviews_items},
            {"type": "faq", "kicker": "FAQ", "title": "Частые вопросы", "items": faq_items},
            {"type": "contacts", "kicker": "Контакты",
             "title": f"Оставьте заявку{(' — ' + city_nom) if city_nom else ''}",
             "text": "Перезвоним в течение 15 минут в рабочее время, ответим на вопросы и назовём точную стоимость.",
             "fields": ["name", "phone", "comment"]},
        ],
    }
