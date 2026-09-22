"""Демо-генератор контента: собирает сайт по анкете без LLM.

Нужен, чтобы прототип полностью работал без API-ключа (и как фолбэк,
если RouterAI недоступен). В боевом режиме контент отдаёт модель по prompts.py.
"""
import re

try:
    import niches
except ModuleNotFoundError:
    from sitegen import niches

# «в Москве» (как в тексте) -> «Москва» (именительный, для подписей)
CITY_NOM = {"Москве": "Москва", "Москвы": "Москва", "Москва": "Москва",
            "Санкт-Петербурге": "Санкт-Петербург", "Санкт-Петербурга": "Санкт-Петербург", "СПб": "Санкт-Петербург",
            "Казани": "Казань", "Казань": "Казань",
            "Екатеринбурге": "Екатеринбург", "Екатеринбург": "Екатеринбург",
            "Новосибирске": "Новосибирск", "Новосибирск": "Новосибирск",
            "Раменском": "Раменское", "Краснодаре": "Краснодар", "Краснодар": "Краснодар",
            "Сочи": "Сочи", "Челябинске": "Челябинск", "Челябинск": "Челябинск",
            "Нижнем Новгороде": "Нижний Новгород", "Нижний Новгород": "Нижний Новгород",
            "Самаре": "Самара", "Самара": "Самара",
            "Ростове-на-Дону": "Ростов-на-Дону", "Ростове": "Ростов-на-Дону",
            "Уфе": "Уфа", "Уфа": "Уфа",
            "Твери": "Тверь", "Владивостоке": "Владивосток", "Перми": "Пермь", "Тюмени": "Тюмень", "Омске": "Омск",
            "Воронеже": "Воронеж", "Воронеж": "Воронеж", "Калининграде": "Калининград", "Ярославле": "Ярославль"}

PRICE_RE = re.compile(r"\s*[-—–=]\s*|\s+по\s+(\d|\d[\d\s]{1,7})\s*(₽|руб)", re.I)
TAIL_PRICE_RE = re.compile(
    r"\s*[-—–]\s*(от|до)?\s*(\d[\d\s]{1,7})\s*(₽|руб|р\.|тыс)?", re.I)


def extract_city(text: str):
    """Возвращает (именительный, фраза_с_предлогом): («Москва», «в Москве»)."""
    t = text or ""
    # сначала проверяем известные формы (включая родительный «Москвы»)
    for prep, nom in CITY_NOM.items():
        # ищем как отдельное слово
        if re.search(r"\b" + re.escape(prep) + r"\b", t):
            # для именительного отдаем предложный «в Москве», для родительного тоже
            # ищем предложный вариант для этого города
            pref = None
            for k,v in CITY_NOM.items():
                if v==nom and k.endswith("е") or k.endswith("и"):
                    # эвристика: предложный оканчивается на е/и
                    if "Москве" in k or "Петербурге" in k or k in ("Казани","Самаре","Уфе"):
                        pref=k; break
            if not pref:
                pref = prep if prep != nom else next((k for k,v in CITY_NOM.items() if v==nom and k!=nom), prep)
            # если prep уже предложный, используем его
            if prep in ("Москве","Санкт-Петербурге","Казани","Екатеринбурге","Новосибирске","Краснодаре","Самаре","Уфе"):
                return nom, f"в {prep}"
            # родительный «Москвы» -> «в Москве»
            if prep in ("Москвы","Санкт-Петербурга"):
                return nom, f"в {'Москве' if nom=='Москва' else 'Санкт-Петербурге'}"
            return nom, f"в {pref}"
        if re.search(r"\b" + re.escape(nom) + r"\b", t):
            # нашли именительный — возвращаем предложный
            for p2, n2 in CITY_NOM.items():
                if n2 == nom and p2 != nom:
                    # предпочитаем форму на «е/и»
                    if p2.endswith("е") or p2.endswith("и"):
                        return nom, f"в {p2}"
            for p2, n2 in CITY_NOM.items():
                if n2 == nom and p2 != nom:
                    return nom, f"в {p2}"
            return nom, f"в {nom}"
    m = re.search(r"\b(?:в|г\.\s?|городе?\s+)\s*([А-ЯЁ][а-яё\-]{2,})", t)
    if m:
        cand = m.group(1)
        # если похоже на Москву в родительном, мапим
        if cand.lower() in ("москвы","москве","москва"):
            return "Москва", "в Москве"
        if cand.lower().startswith("петербург"):
            return "Санкт-Петербург", "в Санкт-Петербурге"
        return cand, f"в {cand}"
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
    # Try to use advantage for hero title benefit
    benefit = ""
    if advantages:
        # pick advantage with numbers or guarantee
        for adv in advantages:
            if re.search(r"\d|гарант|минут|час|день", adv, re.I):
                benefit = adv.strip()[:36]
                break
        if not benefit:
            benefit = advantages[0].strip()[:36]
    # Build hero title: benefit + city, not generic
    if benefit:
        hero_title = f"{first_short[0].upper() + first_short[1:]} — {benefit.lower()}"
        if city_in and city_in not in hero_title:
            hero_title += f" {city_in}"
        hero_title = hero_title.replace("  ", " ").strip()[:70]
    else:
        hero_title = f"{first_short[0].upper() + first_short[1:]} {city_in} — быстро и с гарантией".replace("  ", " ") \
            if city_in else f"{first_short[0].upper() + first_short[1:]} — быстро и с гарантией"
    about_short = about_text.rstrip(". ")
    if 25 < len(about_short) <= 170 and about_short.lower()[:12] != name.lower()[:12]:
        hero_sub = f"{name} — {about_short}. Работаем по договору, стоимость фиксируем до начала работ."
    elif about_short:
        hero_sub = f"{about_short}. Работаем по договору, стоимость фиксируем до начала работ."
    else:
        hero_sub = f"{name}: работаем по договору, стоимость фиксируем до начала работ."
    # More concrete stats from advantages
    hero_stats = []
    # Try to extract numbers from advantages for stats
    for adv in (advantages or [])[:3]:
        m=re.search(r"(\d+\s*(?:лет|год|мес|дн|час|мин|%|₽|клиент|заказ|гарант))", adv, re.I)
        if m:
            hero_stats.append({"value": m.group(1).strip()[:16], "label": adv.strip()[:32]})
        else:
            # fallback generic but more specific
            hero_stats.append({"value": adv.strip()[:16], "label": "преимущество"})
    # Fill up to 3 with defaults if needed
    defaults = [{"value": "15 мин", "label": "отвечаем на заявку"},
                {"value": "1 год", "label": "гарантия по договору"},
                {"value": "0 ₽", "label": "диагностика"}]
    while len(hero_stats) < 3:
        hero_stats.append(defaults[len(hero_stats)])
    hero_stats=hero_stats[:3]

    # ---------- services ----------
    services_items = []
    for p in (prod_lines or [{"name": n, "price": ""} for n in bank["products"][:6]]):
        # More concrete desc: use extra bullet if available
        extra = ""
        if extras:
            extra = f" {extras[0]}." if len(extras[0]) < 40 else ""
        services_items.append({
            "name": p["name"],
            "desc": f"{p['name']}: диагностика и смета до начала, фиксируем цену.{extra}",
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
    # Try to make reviews more niche-specific
    city_suffix = f" {city_in}" if city_in else ""
    reviews_items = [
        {"name": "Мария Р.", "meta": f"{first_service}{city_suffix}, июль 2026",
         "text": f"Обратились в «{name}» по рекомендации{city_suffix}. Смету дали до начала работ, "
                 "сделали в срок, цена не изменилась ни на рубль."},
        {"name": "Олег Л.", "meta": f"Повторный заказ{city_suffix}, март 2026",
         "text": f"Понравилось, что держали в курсе каждый этап{(' и присылали фото' if niche in ('build','auto') else '')}. "
                 "Вопросы решали сразу, без «завтра сделаем»."},
        {"name": "Елена К.", "meta": f"Срочный заказ{city_suffix}, август 2026",
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
    """DEPRECATED: taplink убран — QR-визитка покрывает мультиссылку.
    Оставлен как alias к build_vcard_site для обратной совместимости (старые тесты/данные)."""
    site = build_vcard_site(answers, theme_mode, accent)
    # сохраняем возможность отдавать kind taplink для старых проверок, но новый API
    # мапит taplink→vcard; если вызов пришёл как taplink — вернём vcard с линками
    # для совместимости помечаем badges как Taplink если в about есть ссылки
    return site


def build_vcard_site(answers: dict, theme_mode: str, accent: str) -> dict:
    """QR-визитка / myqrcards + мультиссылка (объединено: QR-визитка покрывает taplink)."""
    a = lambda key: answers.get(key) or answers.get(
        {"Название": "name", "О бизнесе": "about", "Услуги/товары": "products",
         "Преимущества": "advantages", "Дополнительно": "extras", "Должность": "position",
         "Компания": "company", "Ссылки": "links"}[key]) or ""
    name = a("Название").strip() or "Иван Петров"
    company = a("Компания").strip() or a("О бизнесе").strip()[:40] or "Компания"
    position = a("Должность").strip() or "Менеджер"
    about_text = a("О бизнесе").strip() or f"{name} — {position} в {company}"
    phone = "+7 (900) 123-45-67"
    email = f"hello@{re.sub(r'[^a-z0-9]', '', name.lower())[:10] or 'example'}.ru"
    extras = a("Дополнительно").strip() or ""
    # ссылки: из поля products/ссылки — как в taplink (каждая с новой строки)
    links_raw = a("Услуги/товары") or a("Ссылки") or ""
    links = []
    # если в products явно ссылки (содержат http или «— https»)
    if links_raw and ("http" in links_raw or " — " in links_raw or " - " in links_raw):
        for raw in re.split(r"[\n;]+", links_raw):
            raw = raw.strip()
            if not raw or len(raw) < 3:
                continue
            m = re.search(r"(https?://\S+)", raw)
            if m:
                url = m.group(1)
                title = raw.replace(url, "").strip(" -—–|")
                if not title:
                    title = url
            else:
                title = raw[:60]
                url = "https://example.com/" + re.sub(r"\W+", "-", title.lower()).strip("-")
            links.append({"title": title[:60], "url": url[:200], "subtitle": "", "icon": "🔗", "style": "filled"})
            if len(links) >= 8:
                break
    # также пробуем вытащить соцсети/ссылки из advantages если похоже на ссылки
    adv_raw = a("Преимущества") or ""
    if adv_raw and "http" in adv_raw:
        for raw in re.split(r"[\n;]+|,", adv_raw):
            raw = raw.strip()
            if "http" in raw and len(links) < 8:
                m = re.search(r"(https?://\S+)", raw)
                if m:
                    url = m.group(1)
                    title = raw.replace(url, "").strip(" -—–|") or url
                    links.append({"title": title[:60], "url": url[:200], "subtitle": "", "icon": "🔗", "style": "filled"})
    socials = [
        {"platform": "telegram", "url": "https://t.me/example", "label": "Telegram"},
        {"platform": "whatsapp", "url": "https://wa.me/79001234567", "label": "WhatsApp"},
        {"platform": "instagram", "url": "https://instagram.com/example", "label": "Instagram"},
    ]
    messengers = [
        {"platform": "whatsapp", "url": "https://wa.me/79001234567", "label": "WhatsApp", "handle": "+7 900 123-45-67"},
        {"platform": "telegram", "url": "https://t.me/example", "label": "Telegram", "handle": "@example"},
        {"platform": "phone", "url": "tel:+79001234567", "label": "Позвонить", "handle": "+7 900 123-45-67"},
    ]
    # секции: profile + qrcode + (tap_links если есть) + vcard + socials + messengers + tap_text + contacts
    sections = [
        {"type": "profile", "name": name, "subtitle": f"{position} · {company}", "bio": about_text[:200], "badges": ["QR-визитка", company] if company else ["QR-визитка"]},
        {"type": "qrcode", "kicker": "QR-код", "title": "Сохраните контакт", "text": "Наведите камеру, чтобы сохранить визитку", "data": f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nORG:{company}\nTEL:{phone}\nEMAIL:{email}\nEND:VCARD", "note": "Работает без приложения"},
    ]
    if links:
        sections.append({"type": "tap_links", "kicker": "Ссылки", "title": "Мои ссылки", "items": links})
    sections.extend([
        {"type": "vcard", "kicker": "Контакты", "title": "Как связаться", "items": [
            {"label": "Телефон", "value": phone, "href": f"tel:{phone}", "icon": "phone"},
            {"label": "Email", "value": email, "href": f"mailto:{email}", "icon": "chat"},
            {"label": "Компания", "value": company, "href": "", "icon": "team"},
            {"label": "Адрес", "value": extras[:60] if extras else "Москва", "href": "", "icon": "map"},
        ]},
        {"type": "socials", "kicker": "Соцсети", "title": "Я в соцсетях", "items": socials},
        {"type": "messengers", "kicker": "Связаться", "title": "Напишите мне", "items": messengers},
        {"type": "tap_text", "kicker": "", "title": "", "text": extras[:200] if extras else "Буду рад знакомству — пишите в любой мессенджер."},
        {"type": "contacts", "kicker": "Заявка", "title": "Оставьте контакты", "text": "Перезвоню и отвечу на вопросы.", "fields": ["name", "phone", "comment"]},
    ])
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
        "nav": [{"label": "Ссылки", "href": "#links"}, {"label": "Контакты", "href": "#contacts"}],
        "sections": sections,
        "features": {"cart": False},
    }
