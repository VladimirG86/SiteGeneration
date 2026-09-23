"""Демо-генератор + рендер: прогон по всем нишам без LLM и сети."""
import re

import chat
import demo_content
import sections

CASES = [
    ("АвтоПрофи", "Автосервис в Казани, ремонт двигателей с 2015 года", "Диагностика - 1500", "Гарантия 12 месяцев", "auto"),
    ("Улыбка+", "Стоматология в Москве, лечение и имплантация", "Чистка - 5000", "Лечение без боли", "dental"),
    ("Шарм", "Салон красоты в СПб", "Стрижка - 1800", "Мастера с портфолио", "beauty"),
    ("Brewhaus", "Кофейня в Екатеринбурге, своя обжарка", "Латте - 280", "Готовим при вас", "food"),
    ("Атлант", "Фитнес-клуб в Новосибирске", "Абонемент - 3500", "Пробная бесплатно", "fitness"),
    ("ДомСтрой", "Строительство домов в Краснодаре", "Проект - бесплатно", "Договор", "build"),
    ("Лингва", "Школа английского в Самаре", "Группа - 8000", "Пробное бесплатно", "edu"),
    ("МедЛайн", "Медцентр в Уфе: диагностика, МРТ", "МРТ - от 6000", "Результаты в день", "med"),
    ("ПравоВед", "Юристы в Ростове-на-Дону", "Консультация - 3000", "Опыт 15 лет", "law"),
    ("Квадрат", "Агентство недвижимости в Сочи", "Подбор - 2%", "Проверка чистоты", "realestate"),
    ("Пиксель", "Веб-студия в Перми", "Лендинг - от 60000", "Запуск за 14 дней", "it"),
    ("Пустышка", "Короткое описание без деталей вообще", "", "", "generic"),
]


def test_all_niches_build_and_render():
    for i, (name, about, prod, adv, niche) in enumerate(CASES):
        site = demo_content.build_site(
            {"Название": name, "О бизнесе": about, "Услуги/товары": prod,
             "Преимущества": adv, "Дополнительно": ""},
            "dark" if i % 2 else "light", ["blue", "emerald", "orange"][i % 3])
        assert site["niche"] == niche, name
        site = chat.normalize_site(site)
        types = [s["type"] for s in site["sections"]]
        assert types[0] == "hero" and types[-1] == "contacts", name
        html = sections.render_page(dict(site), site_id=f"t{i}")
        assert "<html" in html and "lead-form" in html and len(html) > 15000, name


def test_duplicate_blocks_get_unique_anchors():
    site = chat.normalize_site(demo_content.build_site(
        {"Название": "T", "О бизнесе": "Кофейня в Казани.", "Услуги/товары": "Латте - 100",
         "Преимущества": "Вкусно", "Дополнительно": ""}, "light", "blue"))
    chat.apply_ops(site, [{"op": "add_section", "section": {
        "type": "faq", "title": "Ещё FAQ", "items": [{"q": "q?", "a": "a"}]}}])
    html = sections.render_page(dict(site), site_id="dup")
    assert 'id="faq"' in html and 'id="faq-2"' in html
    # все id в документе уникальны
    ids = re.findall(r'id="([^"]+)"', html)
    assert len(ids) == len(set(ids)), ids

def test_hero_benefit_and_stats_from_advantages():
    # advantage with numbers should flow into hero title and stats
    site=demo_content.build_site({"Название":"Кофейня Утро","О бизнесе":"Кофейня в центре Москвы, своя обжарка с 2019","Услуги/товары":"Капучино - 200","Преимущества":"Гарантия 12 месяцев\nОтвечаем за 15 минут\n500 клиентов","Дополнительно":""}, "light","orange")
    hero=[s for s in site["sections"] if s["type"]=="hero"][0]
    # title should contain benefit fragment
    assert "гарантия 12" in hero["title"].lower()
    # stats should be concrete from advantages, not generic
    stats=hero.get("stats",[])
    assert len(stats)==3
    assert any("12" in s["value"] for s in stats)
    assert any("15" in s["value"] for s in stats)

def test_hero_fallback_without_advantages():
    site=demo_content.build_site({"Название":"Кофейня Утро","О бизнесе":"Кофейня","Услуги/товары":"Капучино - 200","Преимущества":"","Дополнительно":""}, "light","orange")
    hero=[s for s in site["sections"] if s["type"]=="hero"][0]
    assert hero["title"] and len(hero["title"])<=70
    assert len(hero.get("stats",[]))==3

def test_tariffs_exposed_in_config(client):
    r=client.get("/api/config")
    assert r.status_code==200
    j=r.json()
    assert "tariffs" in j
    assert "pro" in j["tariffs"]
    assert "tariffs_meta" in j
    assert j["tariffs_meta"]["paused"] is True
    assert "pro" in j["tariffs_meta"]["limits"]

def test_nelvi_hero_and_niche_regression():
    # регрессия: лендинг + автоматом не должен детектиться как auto, hero не должен обрезаться до 16 симв
    site=demo_content.build_site({"Название":"Nelvi — конструктор сайтов за вечер","О бизнесе":"Сервис для создания лендингов, QR-визиток и свободных канвасов без кода. Собирай страницы блоками, публикуй в один клик, принимай заявки и не думай про хостинг, домен и SSL.","Услуги/товары":"Лендинг за 5 минут — от 0 ₽\nQR-визитка — Taplink\nСвободный канвас — как в Tilda","Преимущества":"Без кода и дизайнеров — как конструктор\nПубликация в 1 клик — поддомен и SSL автоматом\nИмпорт любого сайта по ссылке — клонируем и правим чатом","Дополнительно":""}, "light","purple")
    assert site["niche"] == "it", site["niche"]
    hero=[s for s in site["sections"] if s["type"]=="hero"][0]
    assert hero["title"] == "Сайт за вечер. Без кода."
    # stats: value должен быть ✓, а label — полный (до 48), без обрезки до 16
    for st in hero["stats"]:
        assert st["value"] == "✓"
        assert len(st["label"]) > 16
        assert "Без кода и дизай" not in st["value"]  # старый баг adv[:16]

def test_billing_limits():
    import billing
    pro = billing.limits_for("pro")
    assert pro["price_m"] == 1990
    assert pro["featured"] is True
    assert pro["sites"] == 20
    assert billing.limits_for("free")["price_m"] == 0
    assert billing.checkout_url("pro") == "/#prices?tariff=pro"
    assert billing.checkout_url("pro", yearly=True) == "/#prices?tariff=pro&yearly=1"

def test_swedish_phone_preserved():
    site = demo_content.build_site({"Название":"Test","О бизнесе":"Кофейня в Стокгольме","Услуги/товары":"Кофе","Преимущества":"","Дополнительно":"+46 8 123 45 67"}, "light","purple")
    assert "+46" in site["phone"]

