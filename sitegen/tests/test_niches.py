"""Детектор ниш: регрессия по ложным срабатываниям substring-поиска."""
import niches

CASES = [
    ("Сервис для создания лендингов, QR-визиток без кода — публикация в 1 клик, поддомен и SSL автоматом", "it"),  # лендинг → it, автоматом ≠ авто
    ("АвтоПрофи Ремонт двигателей в Казани СТО", "auto"),
    ("СТО в Раменском, шиномонтаж", "auto"),
    ("Медцентр в Уфе: диагностика и врачи, МРТ, приём терапевта", "med"),
    ("Юридические услуги для бизнеса в Ростове-на-Дону", "law"),
    ("Агентство недвижимости в Сочи, подбор квартиры", "realestate"),
    ("Ремонт квартир в Казани под ключ", "build"),
    ("Йогурты и десерты, кофейня", "food"),  # йогурт ≠ йога
    ("Школа английского для детей", "edu"),
    ("Стоматология, имплантация", "dental"),
    ("Фитнес-клуб, йога и групповые", "fitness"),
    ("Салон красоты, маникюр", "beauty"),
    ("Веб-студия, SEO и реклама", "it"),
    ("абырвалг непонятное описание", "generic"),
    ("Кофейня в Стокгольме, доставка выпечки", "food"),  # Stockholm — интл город, не приоритет но food должен детектиться
    ("Сервис в Стокгольме: лендинг + QR", "it"),  # Stockholm + it
]


def test_detect_all():
    for text, want in CASES:
        assert niches.detect_niche(text) == want, text


def test_chips_shape():
    for niche in list(niches.NICHE_KEYWORDS) + ["generic", "nope"]:
        chips = niches.chips_for(niche)
        assert set(chips) == {"products", "advantages", "extras"}
        assert all(isinstance(x, str) and x for v in chips.values() for x in v)
