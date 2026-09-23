"""Заглушка биллинга Nelvi через Lava.top (https://developers.lava.top/ru).

Lava: 8% комиссия, без абонплаты. Продукт создаётся с «Цена по запросу API»,
инвойс — POST /api/v3/invoice {offerId, amount, currency, email, return_urls}.

Webhook: payment.success / failed, subscription.recurring.* , subscription.cancelled
— маппим по сумме (период в вебхуке отсутствует, см. PR #170).
"""
import os

# --- тарифы (как в docs/tariffs.md) — 2000 ₽ = Pro 1990 ---
TARIFFS = {
    "free":     {"title": "Free",     "price_m": 0,    "price_y": 0,     "sites": 1,  "edits": 50,   "domain": 0, "label": "Старт"},
    "start":    {"title": "Start",    "price_m": 990,  "price_y": 9900,  "sites": 5,  "edits": 400,  "domain": 1, "label": "Старт"},
    "pro":      {"title": "Pro",      "price_m": 1990, "price_y": 19900, "sites": 20, "edits": 800,  "domain": 5, "label": "Хит", "featured": True},
    "business": {"title": "Business", "price_m": 4990, "price_y": 39900, "sites": 10_000, "edits": 2000, "domain": 99, "label": "Бизнес"},
}

# маппинг Lava amount -> tariff:period (важно: период не приходит в вебхуке, маппим по сумме)
# product_id берётся из app.lava.top после создания продукта с «Цена по запросу API»
LAVA_OFFER_ID = os.environ.get("LAVA_OFFER_ID", "").strip()
LAVA_API_KEY  = os.environ.get("LAVA_API_KEY", "").strip()
LAVA_PRODUCTS = {
    # пример: "836b9fc5-....": {"990": "start:monthly", "9900": "start:yearly", "1990": "pro:monthly", "19900": "pro:yearly", "4990": "business:monthly", "39900": "business:yearly"},
}

def is_configured() -> bool:
    return bool(LAVA_API_KEY and LAVA_OFFER_ID)

def price_for(tariff: str, yearly: bool = False) -> int:
    t = TARIFFS.get(tariff)
    if not t:
        raise ValueError(tariff)
    return t["price_y"] if yearly else t["price_m"]

def resolve_plan(product_id: str, amount) -> str | None:
    """amount -> 'pro:monthly' etc. Не гадаем — неизвестная сумма = None (в журнал)."""
    try:
        amt = str(int(float(amount)))
    except:
        amt = str(amount).strip()
    return (LAVA_PRODUCTS.get(product_id) or {}).get(amt)
