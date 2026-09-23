# Nelvi — тарифы (предложение, сентябрь 2026)

> Основано на анализе VERSTKA.ai (990 / 1990 / 4990 ₽) + твое пожелание **2000 ₽/мес норм**.
> Платежи — через **Lava.top** (комиссия 8% с продажи, https://developers.lava.top/ru).

## Позиционирование
- **Бесплатно** — попробовать, 1 лендинг на поддомене.
- **2000 ₽** — основной (Pro) — безлимит по caйтам в рамках лимита, снятие ватермарки, домен, экспорт.
- Верхний — для студий/команд.

Цены — **RUB**, помесячно, без НДС (ИП/самозанятый). Год — **-20%** (2 мес в подарок).

| Тариф | Цена (мес) | Цена (год) | Сайты | ИИ-правок/мес* | Поддомен | Свой домен + SSL | Экспорт | Что ещё |
|-------|------------|------------|-------|----------------|----------|----------------|---------|---------|
| **Free** | **0 ₽** | — | 1 | 50 | `*.nelvi.app` | — | — | Водяной знак «Сделано на Nelvi», 1 QR-визитка, форма → email |
| **Start** | **990 ₽** | **9 900 ₽** (825/мес) | 5 | 400 | `*.nelvi.app` | ✅ (1 домен) | ZIP | Без ватермарки, S3/WP публикация, Telegram-уведомления |
| **Pro** *(хит)* | **1 990 ₽** | **19 900 ₽** (1 658/мес) | 20 | 800 | `*.nelvi.app` | ✅ (5 доменов) | ZIP + S3 + WP | Приоритет очереди, canvas без лимита, удаление бренда, A/B правки чатом |
| **Business** | **4 990 ₽** | **39 900 ₽** (3 325/мес) | ∞ | 2 000 | `*.nelvi.app` | ✅ (∞) | ZIP + S3 + WP + API | Команда 5 чел, вебхуки, кастомный CNAME, SLA 99.9% |

*ИИ-правка = один `POST /api/chat/{id}` или генерация блока. У VERSTKA.ai лимиты 400/800/2000 — берём те же, знакомо рынку.
Для Fallback (без ключа) лимиты те же, но вместо LLM — `demo_content`.

## Почему 1990, а не ровно 2000
- Психология цены (1990 < 2000), но в разговоре — «около двух тысяч».
- Оставил 990 как низкий вход (конверсия фри→платный +12% по рынку), 4990 — для студий. Если хочешь **только** 2000 — схлопываем Start+Pro в один `Pro 1 990`, Free остаётся.

## Unit-экономика (Lava 8%)
- 1 990 ₽ → на руки **1 830 ₽** (Lava 8% = 159 ₽), минус эквайринг уже внутри.
- Годовой 19 900 → 1 658/мес → на руки 1 525/мес.
- MRR пример: при 100 платящих Pro: **183 тыс. ₽ MRR** чистыми, 1 000 — 1.83 млн.

## Lava — как подключить (техплан, 1 день)

### 1) Создать продукт
- В `app.lava.top` → Продукты → **Цифровой продукт** (или Подписка) → включи **«Цена по запросу API»** → опубликуй. Получишь `offerId` (UUID).
- Для подписок — создай **тариф** с периодами: месяц + год (обязательно цена за месяц, год — галочкой). Запомни цены → они понадобятся для маппинга.

### 2) Инвойс (создание платежа)
```bash
curl -X POST https://gate.lava.top/api/v3/invoice \
  -H "X-Api-Key: $LAVA_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "email": "client@example.com",
    "offerId": "836b9fc5-...-592bc44072b7",
    "currency": "RUB",
    "amount": 1990,
    "successful_return_url": "https://nelvi.app/thanks?tariff=pro",
    "failure_return_url": "https://nelvi.app/pay-failed",
    "cancel_return_url": "https://nelvi.app/checkout"
  }'
# → { "invoiceId": "...", "paymentUrl": "https://pay.lava.top/..." }
```
Редиректи пользователя на `paymentUrl`. Lava добавит `?invoiceId=...&status=success`.

### 3) Webhook
- В `Интеграции → Public API → Добавить Webhook` → URL `https://nelvi.app/api/billing/lava/webhook` → события:
  `payment.success`, `payment.failed`, `subscription.recurring.payment.success`, `subscription.recurring.payment.failed`, `subscription.cancelled`
- Аутентификация — **Basic** (логин/пароль) на наш эндпоинт (только https) или `X-Api-Key`.

**Важно (грабли из PR #170):** в `purchase` вебхуке **нет периода** — только `product.id`, `amount`, `currency`, `contractId`, `buyer`. Месяц/год надо маппить **по сумме**:
```python
LAVA_PRODUCTS = {"<product.id>": {"1990": "pro:monthly", "19900": "pro:yearly", "4990": "business:monthly"}}
plan = LAVA_PRODUCTS[product_id].get(str(int(amount)))
if not plan: log as unmapped (не гадать!)
```

### 4) Бэкенд Nelvi (`sitegen/billing.py` — заглушка уже в репо)
- `POST /api/billing/checkout` → создаёт инвойс в Lava, возвращает `paymentUrl`
- `POST /api/billing/lava/webhook` → проверяет Basic/X-Api-Key, маппит `amount→tariff`, продлевает `subscriptions` (Postgres/Redis), шлёт 200 даже на неизвестные события (иначе ретраи)
- `GET /api/billing/me` → текущий тариф, лимиты, остаток правок

Минималка для теста — 50 ₽/5$/5€, тестовой зоны нет.

## Что добавить на лендинг (секция `prices`)
- 4 карточки как в таблице, `Pro` — `featured`, бейдж «Хит», кнопки `Выбрать` → `POST /api/billing/checkout`
- Под карточками — `Год -20%` свитчер (меняет `amount` на годовой)
- FAQ: «Можно оплатить из-за границы? — Да, Lava принимает мир»

## Примечание (домена нет)
Оплата на паузе до домена — `POST /api/billing/checkout` сейчас `200 {paused:true, url:"/#prices?tariff=pro"}`, кнопки ведут на `#prices` (якорь цен). Как появится домен — `LAVA_API_KEY` в `EnvironmentFile` + вебхук `https://<домен>/api/billing/lava/webhook`.

## Следующие шаги
1) Завести продукт в Lava, дать `offerId` + `LAVA_API_KEY` → я докручу `billing.py` + вебхук.
2) Решить: оставляем 4 тарифа или схлопываем к твоим 2000 (Free+Pro+Business).
3) Годовой — включать сразу или после первых 50 платящих.

---
*Подготовлено для ветки `arena/01a0c97a-sitegeneration`, 2026-09-23 — темп-стенд `185.185.70.64:8002` (`GET /api/health` → `{ok, billing_paused}`).*
