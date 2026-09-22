"""Библиотека секций лендинга: JSON-контент → HTML.

Каждая секция — отдельная функция-рендерер с защитными значениями по умолчанию.
Это «вёрсточная» часть конструктора: модель сюда не допускается, она отдаёт
только данные по схеме. Неизвестный тип секции просто пропускается.
"""
import html
import random
import re

ICONS = {  # простые линейные иконки (stroke)
    "wrench": '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4L15 12l-3-3 2.7-2.7z"/>',
    "shield": '<path d="M12 3l7 3v5c0 5-3.5 8-7 10-3.5-2-7-5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
    "star": '<path d="M12 3l2.7 5.7 6.3.9-4.5 4.4 1 6-5.5-2.9L6.5 20l1-6L3 9.6l6.3-.9L12 3z"/>',
    "rub": '<path d="M7 20h6a4 4 0 0 0 0-8H9V4h5"/><path d="M9 12H6"/><path d="M7 16h6"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a12 12 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    "map": '<path d="M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "doc": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/><path d="M10 12h5M10 16h5"/>',
    "team": '<circle cx="9" cy="8" r="3"/><path d="M4 20a5 5 0 0 1 10 0"/><circle cx="17" cy="9" r="2.4"/><path d="M14.5 20a4.5 4.5 0 0 1 7-3.7"/>',
    "spark": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z"/>',
    "cart": '<circle cx="9" cy="20" r="1.6"/><circle cx="17" cy="20" r="1.6"/><path d="M3 4h2l2.5 11h10L20 8H6"/>',
    "home": '<path d="M4 11l8-7 8 7"/><path d="M6 10v10h12V10"/>',
    "search": '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    "chat": '<path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"/>',
    "card": '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18"/>',
    "gift": '<rect x="4" y="9" width="16" height="11" rx="1.5"/><path d="M12 9v11M4 13h16"/><path d="M12 9c-4 0-5-2-4.5-3.7C8 3.6 10.6 4.4 12 9zm0 0c4 0 5-2 4.5-3.7C16 3.6 13.4 4.4 12 9z"/>',
}
ICON_KEYS = list(ICONS)


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def icon(name: str) -> str:
    path = ICONS.get(name, ICONS["spark"])
    return (f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{path}</svg>')


def _icon_for(text: str, idx: int) -> str:
    """Подбирает иконку по ключевым словам, иначе по счётчику."""
    t = text.lower()
    for kw, name in (("гарант", "shield"), ("срок", "clock"), ("цен", "rub"),
                     ("звон", "phone"), ("адрес", "map"), ("договор", "doc"),
                     ("опыт", "team"), ("качест", "star"), ("запчас", "wrench"),
                     ("достав", "cart"), ("онлайн", "chat"), ("оплат", "card"),
                     ("бонус", "gift"), ("подбор", "search")):
        if kw in t:
            return name
    return ICON_KEYS[idx % len(ICON_KEYS)]


# ---------------------------------------------------------------- секции ----

def header(site) -> str:
    brand = esc(site.get("brand") or "Компания")
    initial = esc(brand.strip()[:1].upper() or "К")
    nav = site.get("nav") or [{"label": "Услуги", "href": "#services"},
                             {"label": "Цены", "href": "#prices"},
                             {"label": "О нас", "href": "#about"},
                             {"label": "Контакты", "href": "#contacts"}]
    links = "".join(f'<a href="{esc(n.get("href", "#"))}">{esc(n.get("label", ""))}</a>'
                    for n in nav[:5])
    cta = ""
    for s in site.get("sections", []):
        if s.get("type") == "hero":
            cta = s.get("cta_primary") or "Оставить заявку"
            break
    return f"""
<header class="hdr"><div class="wrap hdr-in">
  <a class="logo" href="#"><span class="logo-mark">{initial}</span>{brand}</a>
  <nav class="nav" id="nav">{links}</nav>
  <a class="btn" href="#contacts">{esc(cta)}</a>
  <button class="burger" onclick="document.getElementById('nav').classList.toggle('open')">☰</button>
</div></header>"""


def hero(site, s) -> str:
    title = esc(s.get("title") or site.get("brand", "Наш сервис"))
    subtitle = esc(s.get("subtitle") or "")
    c1 = esc(s.get("cta_primary") or "Оставить заявку")
    c2 = esc(s.get("cta_secondary") or "Подробнее")
    badges = "".join(f'<span class="badge">{esc(b)}</span>' for b in (s.get("badges") or [])[:4])
    stats = s.get("stats") or []
    stat_html = ""
    if stats:
        stat_html = "<div class='stats'>" + "".join(
            f"<div class='stat'><b>{esc(st.get('value', ''))}</b><span>{esc(st.get('label', ''))}</span></div>"
            for st in stats[:3]) + "</div>"
    art_svg = """<svg viewBox="0 0 400 400" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".16"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient></defs>
    <circle cx="330" cy="60" r="150" fill="url(#g1)"/>
    <circle cx="60" cy="330" r="190" fill="#00000018"/>
    <path d="M0 300 Q120 220 210 290 T420 260 V400 H0 Z" fill="#ffffff22"/>
    <path d="M0 330 Q140 260 240 320 T420 300 V400 H0 Z" fill="#ffffff2e"/>
  </svg>"""
    job = site.get("_job")
    if site.get("hero_image") and job:
        from images import data_uri
        uri = data_uri(job, "hero.webp")
        if uri:
            art_svg = f'<img class="hero-photo" src="{uri}" alt="">'
    art = f"""
<div class="hero-art">
  {art_svg}
  <div class="hero-card">{esc(site.get('tagline') or 'Работаем для вас каждый день')} · <b>{esc(site.get('phone') or 'заявка с сайта')}</b></div>
</div>"""
    return f"""
<section class="hero"><div class="wrap hero-grid">
  <div>
    <h1>{title}</h1>
    <p class="lead">{subtitle}</p>
    <div class="hero-cta">
      <a class="btn" href="#contacts">{c1}</a>
      <a class="btn ghost" href="#prices">{c2}</a>
    </div>
    <div class="badges">{badges}</div>
    {stat_html}
  </div>
  {art}
</div></section>"""


def services(site, s) -> str:
    items = s.get("items") or []
    cards = []
    for i, it in enumerate(items[:9]):
        ic = _icon_for(it.get("name", ""), i)
        price = f'<span class="price-tag">{esc(it["price"])}</span>' if it.get("price") else ""
        cards.append(f"""
<div class="card">
  <div class="icon">{icon(ic)}</div>
  <h3>{esc(it.get('name', ''))}</h3>
  <p>{esc(it.get('desc', ''))}</p>
  {price}
</div>""")
    cls = "c3" if len(cards) > 2 else "c2"
    return f"""
<section class="section alt" id="services"><div class="wrap">
  <span class="kicker">{esc(s.get('kicker') or 'Услуги')}</span>
  <h2>{esc(s.get('title') or 'Что мы делаем')}</h2>
  <div class="grid {cls}">{''.join(cards)}</div>
</div></section>"""


def advantages(site, s) -> str:
    items = s.get("items") or []
    rows = []
    for i, it in enumerate(items[:6]):
        ic = _icon_for(it.get("title", "") + " " + it.get("desc", ""), i)
        rows.append(f"""
<div class="check-item">
  <div class="icon">{icon(ic)}</div>
  <div><h3>{esc(it.get('title', ''))}</h3><p>{esc(it.get('desc', ''))}</p></div>
</div>""")
    return f"""
<section class="section" id="advantages"><div class="wrap">
  <span class="kicker">{esc(s.get('kicker') or 'Почему мы')}</span>
  <h2>{esc(s.get('title') or 'Наши преимущества')}</h2>
  <div class="grid c2">{''.join(rows)}</div>
</div></section>"""


def about(site, s) -> str:
    paras = "".join(f"<p>{esc(p)}</p>" for p in (s.get("paragraphs") or [])[:4])
    bullets = "".join(f"""<div class="bullet">{icon('star')}<span>{esc(b)}</span></div>"""
                      for b in (s.get("bullets") or [])[:5])
    return f"""
<section class="section alt" id="about"><div class="wrap">
  <span class="kicker">{esc(s.get('kicker') or 'О компании')}</span>
  <h2>{esc(s.get('title') or 'О нас')}</h2>
  <div class="about-grid">
    <div class="paragraphs">{paras}</div>
    <div class="bullets">{bullets}</div>
  </div>
</div></section>"""


def process(site, s) -> str:
    steps = "".join(f"""<div class="step"><h3>{esc(st.get('title', ''))}</h3>
      <p>{esc(st.get('desc', ''))}</p></div>"""
                    for st in (s.get("steps") or [])[:5])
    return f"""
<section class="section" id="process"><div class="wrap">
  <span class="kicker">{esc(s.get('kicker') or 'Как мы работаем')}</span>
  <h2>{esc(s.get('title') or 'Как проходит работа')}</h2>
  <div class="steps">{steps}</div>
</div></section>"""


def prices(site, s) -> str:
    items = s.get("items") or []
    cards = []
    for it in items[:4]:
        feat = " featured" if it.get("featured") else ""
        li = "".join(f"<li>{icon('star')}<span>{esc(x)}</span></li>" for x in (it.get("includes") or [])[:5])
        btn = "Выбрать" if not it.get("featured") else "Оставить заявку"
        cards.append(f"""
<div class="card price-card{feat}">
  <h3>{esc(it.get('name', ''))}</h3>
  <div class="price">{esc(it.get('price', 'по запросу'))}</div>
  <p>{esc(it.get('desc', ''))}</p>
  <ul>{li}</ul>
  <a class="btn{' ghost' if not it.get('featured') else ''}" href="#contacts">{btn}</a>
</div>""")
    cls = "c3" if len(cards) >= 3 else "c2"
    note = f"<div class='price-note'>{esc(s['note'])}</div>" if s.get("note") else ""
    return f"""
<section class="section alt" id="prices"><div class="wrap">
  <span class="kicker">{esc(s.get('kicker') or 'Цены')}</span>
  <h2>{esc(s.get('title') or 'Цены на услуги')}</h2>
  <div class="grid {cls}">{''.join(cards)}</div>
  {note}
</div></section>"""


def reviews(site, s) -> str:
    items = s.get("items") or []
    cards = []
    for it in items[:6]:
        name = esc(it.get("name", "Клиент"))
        initials = esc("".join(w[0] for w in name.split()[:2]).upper())
        cards.append(f"""
<div class="card">
  <div class="review-stars">★★★★★</div>
  <p style="margin-top:10px">{esc(it.get('text', ''))}</p>
  <div class="review-meta">{esc(it.get('meta', ''))}</div>
  <div class="review-name"><span class="avatar">{initials}</span>{name}</div>
</div>""")
    cls = "c3" if len(cards) >= 3 else "c2"
    return f"""
<section class="section" id="reviews"><div class="wrap">
  <span class="kicker">{esc(s.get('kicker') or 'Отзывы')}</span>
  <h2>{esc(s.get('title') or 'Что говорят клиенты')}</h2>
  <div class="grid {cls}">{''.join(cards)}</div>
</div></section>"""


def faq(site, s) -> str:
    rows = "".join(f"""<details><summary>{esc(it.get('q', ''))}</summary>
      <p>{esc(it.get('a', ''))}</p></details>"""
                   for it in (s.get("items") or [])[:7])
    return f"""
<section class="section alt" id="faq"><div class="wrap">
  <span class="kicker">{esc(s.get('kicker') or 'FAQ')}</span>
  <h2 style="text-align:center">{esc(s.get('title') or 'Частые вопросы')}</h2>
  <div class="faq-list">{rows}</div>
</div></section>"""


def contacts(site, s, site_id: str = "demo") -> str:
    phone = esc(site.get("phone") or "")
    email = esc(site.get("email") or "")
    address = esc(site.get("address") or "")
    info = ""
    if phone:
        info += f"<div>{icon('phone')}<span>{phone}</span></div>"
    if email:
        info += f"<div>{icon('chat')}<span>{email}</span></div>"
    if address:
        info += f"<div>{icon('map')}<span>{address}</span></div>"
    fields = s.get("fields") or ["name", "phone", "comment"]
    inputs = {
        "name": ('<label>Ваше имя<input type="text" name="name" placeholder="Как к вам обращаться" required></label>'),
        "phone": ('<label>Телефон<input type="tel" name="phone" placeholder="+7 (___) ___-__-__" required></label>'),
        "comment": ('<label>Комментарий<textarea name="comment" rows="3" placeholder="Опишите задачу"></textarea></label>'),
    }
    form_html = "".join(inputs.get(f, "") for f in fields if f in inputs)
    return f"""
<section class="section" id="contacts"><div class="wrap">
 <div class="contact-card">
  <div>
    <span class="kicker" style="background:rgba(255,255,255,.18);color:#fff">{esc(s.get('kicker') or 'Контакты')}</span>
    <h2>{esc(s.get('title') or 'Оставьте заявку')}</h2>
    <p class="lead">{esc(s.get('text') or 'Мы перезвоним в течение рабочего дня и ответим на все вопросы.')}</p>
    <div class="contact-info">{info}</div>
  </div>
  <form class="form" id="lead-form" data-site="{esc(site_id)}">
    {form_html}
    <button class="btn" type="submit">Отправить заявку</button>
    <div class="form-ok" id="form-ok">Спасибо! Заявка отправлена — мы свяжемся с вами.</div>
    <p style="font-size:12px;color:var(--muted);text-align:center">Нажимая кнопку, вы соглашаетесь с политикой конфиденциальности</p>
  </form>
 </div>
</div></section>"""


def products(site, s, cart_enabled=False):
    items = s.get("items") or []
    cards = []
    job = site.get("_job")
    for idx, it in enumerate(items[:12]):
        name = esc(it.get("name", ""))
        price = esc(it.get("price") or "по запросу")
        digits = re.sub(r"[^\d]", "", it.get("price") or "")
        badge = f'<span class="prod-badge">{esc(it["badge"])}</span>' if it.get("badge") else ""
        visual = esc((it.get("emoji") or "🛍️")[:4])
        if it.get("image") and job:
            from images import data_uri
            uri = data_uri(job, f"prod_{idx}.webp")
            if uri:
                visual = f'<img class="prod-photo" src="{uri}" alt="{name}">' 
        if cart_enabled and digits:
            btn = (f'<button class="btn buy-btn" data-name="{name}" data-price="{price}" '
                   f'data-num="{int(digits)}">В корзину</button>')
        else:
            btn = f'<a class="btn ghost" href="#contacts">Узнать подробнее</a>'
        cards.append(f"""
<div class="card prod">
  <div class="prod-img">{visual}{badge}</div>
  <h3>{name}</h3>
  <p>{esc(it.get('desc', ''))}</p>
  <div class="prod-row"><span class="price-tag">{price}</span></div>
  {btn}
</div>""")
    cls = "c3" if len(cards) >= 3 else "c2"
    return f"""
<section class="section alt" id="catalog"><div class="wrap">
  <span class="kicker">{esc(s.get('kicker') or 'Каталог')}</span>
  <h2>{esc(s.get('title') or 'Каталог товаров')}</h2>
  <div class="grid {cls}">{''.join(cards)}</div>
</div></section>"""


def cart_markup(site, site_id: str) -> str:
    """Плавающая корзина + панель оформления (для режима магазина)."""
    return f"""
<button class="cart-fab" id="cart-fab" aria-label="Корзина">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="20" r="1.6"/><circle cx="17" cy="20" r="1.6"/><path d="M3 4h2l2.5 11h10L20 8H6"/></svg>
  <span class="cart-count" id="cart-count" hidden>0</span>
</button>
<div class="cart-overlay" id="cart-overlay" hidden></div>
<aside class="cart-drawer" id="cart-drawer" aria-hidden="true">
  <div class="cart-head"><b>Корзина</b><button class="cart-close" id="cart-close" aria-label="Закрыть">×</button></div>
  <div class="cart-items" id="cart-items"></div>
  <div class="cart-total" id="cart-total" hidden>Итого: <b>0 ₽</b></div>
  <form class="form cart-form" id="cart-form" hidden>
    <label>Ваше имя<input type="text" name="name" placeholder="Как к вам обращаться" required></label>
    <label>Телефон<input type="tel" name="phone" placeholder="+7 (___) ___-__-__" required></label>
    <button class="btn" type="submit">Оформить заказ</button>
    <p style="font-size:12px;color:var(--muted);text-align:center">Оплата после подтверждения — менеджер перезвонит</p>
  </form>
  <div class="cart-empty" id="cart-empty">Корзина пуста. Загляните в <a href="#catalog">каталог</a>.</div>
  <div class="cart-ok" id="cart-ok" hidden>Заказ принят! Мы перезвоним для подтверждения.</div>
</aside>"""


CART_JS = """
<script>
(function(){
  var cart = {};
  var fab = document.getElementById('cart-fab');
  if (!fab) return;
  var drawer = document.getElementById('cart-drawer'),
      overlay = document.getElementById('cart-overlay'),
      itemsBox = document.getElementById('cart-items'),
      totalBox = document.getElementById('cart-total'),
      form = document.getElementById('cart-form'),
      empty = document.getElementById('cart-empty'),
      ok = document.getElementById('cart-ok'),
      countEl = document.getElementById('cart-count');

  function fmt(n){ return n.toLocaleString('ru-RU') + ' \\u20BD'; }
  function totals(){
    var count = 0, sum = 0;
    Object.keys(cart).forEach(function(k){ count += cart[k].qty; sum += cart[k].qty * cart[k].num; });
    return {count: count, sum: sum};
  }
  function render(){
    var html = '', t = totals();
    Object.keys(cart).forEach(function(k){
      var it = cart[k];
      html += '<div class="cart-item"><div class="ci-name">' + it.name +
        '<small>' + fmt(it.num) + '</small></div>' +
        '<div class="ci-qty"><button data-act="dec" data-k="' + k + '">\\u2212</button>' +
        '<span>' + it.qty + '</span>' +
        '<button data-act="inc" data-k="' + k + '">+</button></div>' +
        '<div class="ci-sum">' + fmt(it.num * it.qty) + '</div></div>';
    });
    itemsBox.innerHTML = html;
    countEl.hidden = t.count === 0;
    countEl.textContent = t.count;
    totalBox.hidden = t.count === 0;
    totalBox.querySelector('b').textContent = fmt(t.sum);
    form.hidden = t.count === 0;
    empty.hidden = t.count !== 0 || ok.hidden === false;
    if (t.count > 0) ok.hidden = true;
  }
  function open(v){
    drawer.classList.toggle('open', v);
    overlay.hidden = !v;
    drawer.setAttribute('aria-hidden', String(!v));
    if (v) render();
  }
  document.addEventListener('click', function(e){
    var b = e.target.closest('.buy-btn');
    if (b) {
      var name = b.dataset.name, num = parseInt(b.dataset.num, 10) || 0;
      if (!cart[name]) cart[name] = {name: name, num: num, qty: 0};
      cart[name].qty++;
      render();
      fab.classList.add('bump');
      setTimeout(function(){ fab.classList.remove('bump'); }, 350);
      open(true);
      return;
    }
    var q = e.target.closest('[data-act]');
    if (q) {
      var k = q.dataset.k;
      if (q.dataset.act === 'inc') cart[k].qty++;
      else { cart[k].qty--; if (cart[k].qty <= 0) delete cart[k]; }
      render();
    }
  });
  fab.addEventListener('click', function(){ open(!drawer.classList.contains('open')); });
  document.getElementById('cart-close').addEventListener('click', function(){ open(false); });
  overlay.addEventListener('click', function(){ open(false); });
  form.addEventListener('submit', function(ev){
    ev.preventDefault();
    var data = new FormData(form);
    var items = Object.keys(cart).map(function(k){ return {name: cart[k].name, qty: cart[k].qty, price: cart[k].num}; });
    var body = {
      name: data.get('name'), phone: data.get('phone'),
      comment: 'Заказ из корзины: ' + items.map(function(i){ return i.qty + '\\u00D7 ' + i.name; }).join('; '),
      type: 'cart', items: items
    };
    fetch('API_LEAD_URL', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .catch(function(){});
    cart = {};
    render();
    form.hidden = true; empty.hidden = true; ok.hidden = false;
    countEl.hidden = true;
  });
})();
</script>"""


def footer(site) -> str:
    brand = esc(site.get("brand") or "")
    year = 2026
    phone = esc(site.get("phone") or "")
    return f"""
<footer class="ftr"><div class="wrap ftr-in">
  <span>© {year} {brand}</span>
  {f'<span>{phone}</span>' if phone else ''}
  <span><a href="#/privacy" onclick="return false">Политика конфиденциальности</a></span>
</div></footer>"""


RENDERERS = {
    "hero": hero,
    "services": services,
    "advantages": advantages,
    "about": about,
    "process": process,
    "prices": prices,
    "reviews": reviews,
    "faq": faq,
}


def render_page(site: dict, site_id: str = "demo", theme_mode: str = None,
                accent: str = None) -> str:
    from design import build_css, FONTS_LINK  # локальный импорт против цикла
    theme = site.get("theme") or {}
    theme_mode = theme_mode or theme.get("mode") or "light"
    accent = accent or theme.get("accent") or "purple"
    cart_on = bool((site.get("features") or {}).get("cart"))
    site["_job"] = site_id  # для подстановки изображений (data URI) в секции

    body = [header(site)]
    for s in site.get("sections", []):
        t = s.get("type")
        if t == "contacts":
            body.append(contacts(site, s, site_id))
        elif t == "products":
            body.append(products(site, s, cart_enabled=cart_on))
        elif t in RENDERERS:
            body.append(RENDERERS[t](site, s))
    body.append(footer(site))
    if cart_on:
        body.append(cart_markup(site, site_id))
    brand = esc(site.get("brand") or "Сайт")
    subtitle = ""
    for s in site.get("sections", []):
        if s.get("type") == "hero":
            subtitle = esc(s.get("subtitle", ""))[:160]
            break
    if subtitle.lower().startswith(brand.lower()):
        title_tag = subtitle
    else:
        title_tag = f"{brand} — {subtitle}" if subtitle else brand
    css = build_css(theme_mode, accent)
    lead_js = """
<script>
(function(){
  var f = document.getElementById('lead-form');
  if (!f) return;  // секцию контактов могли удалить в редакторе
  f.addEventListener('submit', async function(e){
    e.preventDefault();
    var data = {};
    new FormData(f).forEach(function(v,k){ data[k]=v; });
    try { await fetch('/api/lead/' + f.dataset.site, {method:'POST',
      headers:{'Content-Type':'application/json'}, body: JSON.stringify(data)});
    } catch(err) {}
    f.querySelectorAll('label,button').forEach(function(el){el.style.display='none'});
    document.getElementById('form-ok').style.display='block';
  });
})();
</script>"""
    cart_js = CART_JS.replace("API_LEAD_URL", f"/api/lead/{esc(site_id)}") if cart_on else ""
    page = f"""<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title_tag}</title>
<meta name="description" content="{subtitle}">
{FONTS_LINK}
<style>{css}</style>
</head><body>
{''.join(body)}
{lead_js}
{cart_js}
</body></html>"""
    site.pop("_job", None)
    return page
