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

# product / offer из https://app.lava.top/products/ecaaca25-df25-4802-85e5-6764dd374f5c/0c6fcc33-81d5-4dc2-a42f-ffed7eef811b (тариф 2000)
LAVA_PRODUCT_ID = os.environ.get("LAVA_PRODUCT_ID", "ecaaca25-df25-4802-85e5-6764dd374f5c").strip()
LAVA_OFFER_ID   = os.environ.get("LAVA_OFFER_ID", "0c6fcc33-81d5-4dc2-a42f-ffed7eef811b").strip()
LAVA_API_KEY    = os.environ.get("LAVA_API_KEY", "").strip()  # не коммитим, задаётся в .env / systemd
# маппинг amount -> tariff:period (период в вебхуке отсутствует, маппим по сумме — PR #170)
LAVA_PRODUCTS = {
    LAVA_PRODUCT_ID: {
        "990": "start:monthly", "9900": "start:yearly",
        "1990": "pro:monthly", "2000": "pro:monthly", "19900": "pro:yearly", "20000": "pro:yearly",
        "4990": "business:monthly", "39900": "business:yearly", "49900": "business:yearly",
        "0": "free:monthly",
    },
    # fallback если продукт придёт без дефисов / нижний регистр — дублируем
    LAVA_PRODUCT_ID.lower(): {
        "990": "start:monthly", "9900": "start:yearly",
        "1990": "pro:monthly", "2000": "pro:monthly", "19900": "pro:yearly", "20000": "pro:yearly",
        "4990": "business:monthly", "39900": "business:yearly",
    },
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
