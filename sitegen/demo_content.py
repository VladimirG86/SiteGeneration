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
        "kind": "landing",
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


def build_taplink_site(answers: dict, theme_mode: str, accent: str) -> dict:
    """Taplink: аватар + ссылки. answers ожидается с ключами name/about/products(ссылки)/extras."""
    a = lambda key: answers.get(key) or answers.get(
        {"Название": "name", "О бизнесе": "about", "Услуги/товары": "products",
         "Преимущества": "advantages", "Дополнительно": "extras", "Ссылки": "links",
         "Соцсети": "socials", "Контакты": "contacts"}[key]) or ""
    name = a("Название").strip() or a("name").strip() or "Иван Петров"
    about_text = a("О бизнесе").strip() or "Помогаю клиентам и делюсь полезным"
    links_raw = a("Услуги/товары") or a("Ссылки") or ""
    # ссылки — каждая с новой строки, возможна форма "Название - https://..."
    links = []
    for raw in re.split(r"[\n;]+", links_raw):
        raw = raw.strip()
        if not raw or len(raw) < 3:
            continue
        # url?
        m = re.search(r"(https?://\S+)", raw)
        if m:
            url = m.group(1)
            title = raw.replace(url, "").strip(" -—–|")
            if not title:
                title = url
        else:
            # без url — делаем заглушку
            title = raw[:60]
            # slug для примера
            url = "https://example.com/" + re.sub(r"\W+", "-", title.lower()).strip("-")
        links.append({"title": title[:60], "url": url[:200], "subtitle": "", "icon": "🔗", "style": "filled"})
        if len(links) >= 8:
            break
    if not links:
        links = [
            {"title": "Мой сайт", "url": "https://example.com", "subtitle": "Портфолио и услуги", "icon": "🌐", "style": "filled"},
            {"title": "Запись на консультацию", "url": "https://t.me/example", "subtitle": "Отвечаю в течение часа", "icon": "✈️", "style": "filled"},
            {"title": "Кейсы и отзывы", "url": "https://example.com/cases", "subtitle": "", "icon": "⭐", "style": "outline"},
        ]
    # соцсети из extras или дефолт
    socials = [
        {"platform": "instagram", "url": "https://instagram.com/example", "label": "Instagram"},
        {"platform": "telegram", "url": "https://t.me/example", "label": "Telegram"},
        {"platform": "whatsapp", "url": "https://wa.me/79001234567", "label": "WhatsApp"},
        {"platform": "youtube", "url": "https://youtube.com/@example", "label": "YouTube"},
    ]
    messengers = [
        {"platform": "whatsapp", "url": "https://wa.me/79001234567", "label": "WhatsApp", "handle": "+7 900 123-45-67"},
        {"platform": "telegram", "url": "https://t.me/example", "label": "Telegram", "handle": "@example"},
        {"platform": "phone", "url": "tel:+79001234567", "label": "Позвонить", "handle": "+7 900 123-45-67"},
    ]
    # небольшой текст
    tap_text = a("Дополнительно").strip() or "Напишите — отвечаю быстро. Все ссылки выше 👆"
    city_nom, city_in = extract_city(about_text + " " + name)
    return {
        "brand": name,
        "city": city_nom,
        "tagline": about_text[:40],
        "phone": "+7 (900) 123-45-67",
        "email": "",
        "address": "",
        "kind": "taplink",
        "avatar_url": "",
        "theme": {"mode": theme_mode, "accent": accent},
        "nav": [{"label": "Ссылки", "href": "#links"}, {"label": "Контакты", "href": "#contacts"}],
        "sections": [
            {"type": "profile", "name": name, "subtitle": about_text[:80] or "Создаю полезный контент", "bio": about_text[:200] or "Добро пожаловать!", "badges": ["Taplink", city_nom] if city_nom else ["Taplink"]},
            {"type": "tap_links", "kicker": "Ссылки", "title": "Мои ссылки", "items": links},
            {"type": "socials", "kicker": "Соцсети", "title": "Я в соцсетях", "items": socials},
            {"type": "messengers", "kicker": "Связаться", "title": "Напишите мне", "items": messengers},
            {"type": "tap_text", "kicker": "", "title": "", "text": tap_text},
            {"type": "contacts", "kicker": "Заявка", "title": "Оставьте контакты", "text": "Перезвоню и отвечу на вопросы.", "fields": ["name", "phone", "comment"]},
        ],
        "features": {"cart": False},
    }


def build_vcard_site(answers: dict, theme_mode: str, accent: str) -> dict:
    """QR-визитка / myqrcards style."""
    a = lambda key: answers.get(key) or answers.get(
        {"Название": "name", "О бизнесе": "about", "Услуги/товары": "products",
         "Преимущества": "advantages", "Дополнительно": "extras", "Должность": "position",
         "Компания": "company"}[key]) or ""
    name = a("Название").strip() or "Иван Петров"
    company = a("Компания").strip() or a("О бизнесе").strip()[:40] or "Компания"
    position = a("Должность").strip() or "Менеджер"
    about_text = a("О бизнесе").strip() or f"{name} — {position} в {company}"
    phone = "+7 (900) 123-45-67"
    email = f"hello@{re.sub(r'[^a-z0-9]', '', name.lower())[:10] or 'example'}.ru"
    extras = a("Дополнительно").strip() or ""
    socials = [
        {"platform": "telegram", "url": "https://t.me/example", "label": "Telegram"},
        {"platform": "whatsapp", "url": "https://wa.me/79001234567", "label": "WhatsApp"},
        {"platform": "instagram", "url": "https://instagram.com/example", "label": "Instagram"},
    ]
    return {
        "brand": name,
        "city": "",
        "tagline": f"{position} · {company}",
        "phone": phone,
        "email": email,
        "address": extras[:80] if extras else "Москва",
        "kind": "vcard",
        "avatar_url": "",
        "theme": {"mode": theme_mode, "accent": accent},
        "nav": [{"label": "Контакты", "href": "#contacts"}],
        "sections": [
            {"type": "profile", "name": name, "subtitle": f"{position} · {company}", "bio": about_text[:200], "badges": ["QR-визитка", company] if company else ["QR-визитка"]},
            {"type": "qrcode", "kicker": "QR-код", "title": "Сохраните контакт", "text": "Наведите камеру, чтобы сохранить визитку", "data": f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nORG:{company}\nTEL:{phone}\nEMAIL:{email}\nEND:VCARD", "note": "Работает без приложения"},
            {"type": "vcard", "kicker": "Контакты", "title": "Как связаться", "items": [
                {"label": "Телефон", "value": phone, "href": f"tel:{phone}", "icon": "phone"},
                {"label": "Email", "value": email, "href": f"mailto:{email}", "icon": "chat"},
                {"label": "Компания", "value": company, "href": "", "icon": "team"},
                {"label": "Адрес", "value": extras[:60] if extras else "Москва", "href": "", "icon": "map"},
            ]},
            {"type": "socials", "kicker": "Соцсети", "title": "Я в соцсетях", "items": socials},
            {"type": "tap_text", "kicker": "", "title": "", "text": extras[:200] if extras else "Буду рад знакомству — пишите в любой мессенджер."},
        ],
        "features": {"cart": False},
    }
