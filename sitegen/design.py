"""Дизайн-система сгенерированных сайтов.

Идея (как у VERSTKA.ai): не «ИИ рисует что попало», а контролируемые
токены темы × библиотека секций. Модель управляет контентом и выбором
темы, вёрстка детерминирована — результат всегда аккуратный.
"""

ACCENTS = {
    "purple":  {"label": "Фиолетовый", "main": "#7c3aed", "dark": "#6d28d9", "soft": "#f1e9fe", "grad": "#06b6d4"},
    "blue":    {"label": "Синий",      "main": "#2563eb", "dark": "#1d4ed8", "soft": "#e7eefe", "grad": "#06b6d4"},
    "emerald": {"label": "Изумруд",    "main": "#059669", "dark": "#047857", "soft": "#e2f6ee", "grad": "#14b8a6"},
    "orange":  {"label": "Оранжевый",  "main": "#ea580c", "dark": "#c2410c", "soft": "#fdeee2", "grad": "#f59e0b"},
    "rose":    {"label": "Малиновый",  "main": "#e11d48", "dark": "#be123c", "soft": "#fde8ed", "grad": "#f97316"},
    "teal":    {"label": "Бирюзовый",  "main": "#0d9488", "dark": "#0f766e", "soft": "#e0f4f2", "grad": "#22d3ee"},
}

MODES = ("light", "dark")

FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)


def build_css(mode: str, accent: str) -> str:
    a = ACCENTS.get(accent, ACCENTS["purple"])
    if mode == "dark":
        vars_ = f"""
      --bg:#0f1424; --bg2:#131a2e; --surface:#171e33; --surface2:#1c2440;
      --text:#f3f5fb; --muted:#a7b1c9; --border:rgba(255,255,255,.09);
      --shadow:0 18px 50px rgba(0,0,0,.45);
      --accent:{a['main']}; --accent-dark:{a['dark']}; --accent-soft:color-mix(in srgb,{a['main']} 18%,transparent);
      --accent-soft2:{a['soft']}; --grad2:{a['grad']};
      --hero-glow:radial-gradient(700px 340px at 75% -10%, {a['main']}33, transparent 70%);
    """
    else:
        vars_ = f"""
      --bg:#ffffff; --bg2:#f6f7fb; --surface:#ffffff; --surface2:#f6f7fb;
      --text:#101528; --muted:#5b6478; --border:#e7e9f2;
      --shadow:0 18px 50px rgba(23,26,63,.10);
      --accent:{a['main']}; --accent-dark:{a['dark']}; --accent-soft:{a['soft']};
      --accent-soft2:{a['soft']}; --grad2:{a['grad']};
      --hero-glow:radial-gradient(700px 340px at 75% -10%, {a['main']}1f, transparent 70%);
    """
    return f"""
    :root{{{vars_}}}
    *{{margin:0;padding:0;box-sizing:border-box}}
    html{{scroll-behavior:smooth}}
    body{{font-family:'Inter',-apple-system,'Segoe UI',Roboto,Arial,sans-serif;
      background:var(--bg);color:var(--text);line-height:1.6;font-size:16px}}
    img,svg{{display:block;max-width:100%}}
    a{{color:inherit;text-decoration:none}}
    .wrap{{max-width:1120px;margin:0 auto;padding:0 24px}}

    /* ---------- header ---------- */
    .hdr{{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--bg) 82%,transparent);
      backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}}
    .hdr-in{{display:flex;align-items:center;gap:28px;height:68px}}
    .logo{{display:flex;align-items:center;gap:10px;font-weight:800;font-size:18px;letter-spacing:-.02em}}
    .logo-mark{{width:34px;height:34px;border-radius:10px;flex:0 0 auto;
      background:linear-gradient(135deg,var(--accent),var(--grad2));color:#fff;
      display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:800}}
    .nav{{display:flex;gap:22px;margin-left:auto;font-size:14.5px;font-weight:500;color:var(--muted)}}
    .nav a:hover{{color:var(--accent)}}
    .hdr .btn{{margin-left:8px}}
    .burger{{display:none;margin-left:auto;background:none;border:1px solid var(--border);
      border-radius:10px;padding:8px 10px;color:var(--text);font-size:16px;cursor:pointer}}

    /* ---------- buttons ---------- */
    .btn{{display:inline-flex;align-items:center;justify-content:center;gap:8px;
      padding:13px 26px;border-radius:12px;font-weight:700;font-size:15.5px;cursor:pointer;
      border:none;color:#fff;background:linear-gradient(120deg,var(--accent),var(--grad2));
      box-shadow:0 10px 24px color-mix(in srgb,var(--accent) 35%,transparent);
      transition:transform .15s ease,box-shadow .15s ease}}
    .btn:hover{{transform:translateY(-2px);box-shadow:0 14px 30px color-mix(in srgb,var(--accent) 45%,transparent)}}
    .btn.ghost{{background:transparent;color:var(--text);border:1.5px solid var(--border);box-shadow:none}}
    .btn.ghost:hover{{border-color:var(--accent);color:var(--accent);transform:none}}

    /* ---------- sections ---------- */
    .section{{padding:84px 0}}
    .section.alt{{background:var(--bg2)}}
    .kicker{{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:700;
      letter-spacing:.08em;text-transform:uppercase;color:var(--accent);
      background:var(--accent-soft);padding:6px 14px;border-radius:999px;margin-bottom:16px}}
    h1{{font-size:clamp(30px,4.6vw,52px);line-height:1.12;letter-spacing:-.03em;font-weight:800}}
    h2{{font-size:clamp(24px,3.2vw,36px);line-height:1.18;letter-spacing:-.025em;font-weight:800;margin-bottom:14px}}
    .lead{{color:var(--muted);font-size:17.5px;max-width:640px}}

    /* ---------- hero ---------- */
    .hero{{position:relative;padding:96px 0 88px;overflow:hidden;background:var(--hero-glow)}}
    .hero-grid{{display:grid;grid-template-columns:1.15fr .85fr;gap:56px;align-items:center}}
    .hero .lead{{margin:20px 0 30px;font-size:18.5px}}
    .hero-cta{{display:flex;gap:14px;flex-wrap:wrap}}
    .badges{{display:flex;flex-wrap:wrap;gap:10px;margin-top:30px}}
    .badge{{font-size:13.5px;font-weight:600;padding:8px 14px;border-radius:999px;
      background:var(--accent-soft);color:var(--accent-dark);border:1px solid color-mix(in srgb,var(--accent) 22%,transparent)}}
    .stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:44px}}
    .stat{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:18px 20px;box-shadow:var(--shadow)}}
    .stat b{{display:block;font-size:26px;letter-spacing:-.02em;color:var(--accent)}}
    .stat span{{font-size:13.5px;color:var(--muted)}}
    .hero-art{{position:relative;border-radius:24px;min-height:380px;overflow:hidden;
      background:linear-gradient(140deg,var(--accent),var(--grad2));box-shadow:var(--shadow)}}
    .hero-photo{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
    .prod-photo{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
    .hero-art svg{{position:absolute;inset:0;width:100%;height:100%}}
    .hero-card{{position:absolute;left:24px;right:24px;bottom:24px;background:var(--surface);
      border-radius:16px;padding:18px 20px;box-shadow:var(--shadow);font-size:14.5px}}
    .hero-card b{{color:var(--accent)}}

    /* ---------- grids & cards ---------- */
    .grid{{display:grid;gap:20px;margin-top:40px}}
    .grid.c3{{grid-template-columns:repeat(3,1fr)}}
    .grid.c2{{grid-template-columns:repeat(2,1fr)}}
    .card{{background:var(--surface);border:1px solid var(--border);border-radius:18px;
      padding:26px;transition:transform .15s ease,box-shadow .15s ease}}
    .card:hover{{transform:translateY(-3px);box-shadow:var(--shadow)}}
    .card h3{{font-size:18px;font-weight:700;margin:14px 0 8px;letter-spacing:-.01em}}
    .card p{{color:var(--muted);font-size:14.5px}}
    .price-tag{{display:inline-block;margin-top:14px;font-weight:800;font-size:15px;color:var(--accent)}}
    .icon{{width:46px;height:46px;border-radius:13px;background:var(--accent-soft);color:var(--accent);
      display:flex;align-items:center;justify-content:center}}
    .icon svg{{width:22px;height:22px}}
    .check-item{{display:flex;gap:12px;align-items:flex-start}}
    .check-item .icon{{flex:0 0 auto;width:38px;height:38px;border-radius:11px}}
    .check-item h3{{margin:2px 0 4px}}

    /* ---------- about ---------- */
    .about-grid{{display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:start;margin-top:8px}}
    .about-grid .paragraphs p{{color:var(--muted);margin-bottom:14px}}
    .bullets{{display:grid;gap:12px}}
    .bullet{{display:flex;gap:12px;align-items:flex-start;background:var(--surface);
      border:1px solid var(--border);border-radius:14px;padding:14px 18px;font-weight:600;font-size:15px}}
    .bullet svg{{width:20px;height:20px;color:var(--accent);flex:0 0 auto;margin-top:2px}}

    /* ---------- process ---------- */
    .steps{{counter-reset:step;display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:20px;margin-top:40px}}
    .step{{background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:24px;position:relative}}
    .step::before{{counter-increment:step;content:counter(step);width:40px;height:40px;border-radius:12px;
      display:flex;align-items:center;justify-content:center;font-weight:800;font-size:17px;color:#fff;
      background:linear-gradient(135deg,var(--accent),var(--grad2));margin-bottom:14px}}
    .step h3{{font-size:16.5px;margin-bottom:6px}}
    .step p{{color:var(--muted);font-size:14px}}

    /* ---------- prices ---------- */
    .price-card{{display:flex;flex-direction:column}}
    .price-card .price{{font-size:28px;font-weight:800;letter-spacing:-.02em;color:var(--accent);margin:10px 0 4px}}
    .price-card ul{{list-style:none;margin:16px 0 22px;display:grid;gap:9px}}
    .price-card li{{display:flex;gap:9px;color:var(--muted);font-size:14.5px}}
    .price-card li svg{{width:18px;height:18px;color:var(--accent);flex:0 0 auto;margin-top:3px}}
    .price-card .btn{{margin-top:auto}}
    .price-card.featured{{border:2px solid var(--accent);position:relative}}
    .price-card.featured::after{{content:'Популярный';position:absolute;top:-13px;left:24px;
      background:linear-gradient(120deg,var(--accent),var(--grad2));color:#fff;font-size:12px;
      font-weight:700;padding:4px 12px;border-radius:999px}}
    .price-note{{text-align:center;color:var(--muted);font-size:13.5px;margin-top:22px}}

    /* ---------- reviews ---------- */
    .review-stars{{color:#f59e0b;letter-spacing:2px;font-size:15px}}
    .review-meta{{margin-top:12px;font-size:13.5px;color:var(--muted);font-weight:600}}
    .review-name{{display:flex;align-items:center;gap:12px;margin-top:16px;font-weight:700;font-size:15px}}
    .avatar{{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--grad2));
      color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px}}

    /* ---------- faq ---------- */
    .faq-list{{max-width:760px;margin:36px auto 0;display:grid;gap:12px}}
    .faq-list details{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:18px 22px}}
    .faq-list summary{{cursor:pointer;font-weight:700;font-size:15.5px;list-style:none;display:flex;justify-content:space-between;gap:16px;align-items:center}}
    .faq-list summary::-webkit-details-marker{{display:none}}
    .faq-list summary::after{{content:'+';font-size:22px;color:var(--accent);font-weight:600;line-height:1}}
    .faq-list details[open] summary::after{{content:'–'}}
    .faq-list details p{{color:var(--muted);margin-top:12px;font-size:14.5px}}

    /* ---------- contacts ---------- */
    .contact-card{{background:linear-gradient(135deg,var(--accent),var(--grad2));border-radius:26px;
      padding:56px;display:grid;grid-template-columns:1fr 1fr;gap:44px;color:#fff;box-shadow:var(--shadow)}}
    .contact-card h2{{color:#fff}}
    .contact-card .lead{{color:rgba(255,255,255,.85)}}
    .contact-info{{display:grid;gap:10px;margin-top:26px;font-size:15px}}
    .contact-info div{{display:flex;gap:10px;align-items:center}}
    .form{{background:var(--surface);border-radius:18px;padding:28px;display:grid;gap:14px;box-shadow:var(--shadow)}}
    .form label{{font-size:13.5px;font-weight:600;color:var(--text);display:grid;gap:6px}}
    .form input,.form textarea{{border:1.5px solid var(--border);background:var(--surface2);color:var(--text);
      border-radius:11px;padding:12px 14px;font:inherit;font-size:15px;outline:none;width:100%}}
    .form input:focus,.form textarea:focus{{border-color:var(--accent)}}
    .form .btn{{width:100%}}
    .form-ok{{display:none;text-align:center;color:var(--accent);font-weight:700;padding:30px 10px}}

    /* ---------- products / shop ---------- */
    .prod{{display:flex;flex-direction:column}}
    .prod-img{{position:relative;height:150px;border-radius:14px;display:flex;align-items:center;justify-content:center;
      font-size:56px;background:linear-gradient(135deg,var(--accent-soft),color-mix(in srgb,var(--accent) 26%,var(--bg2)));overflow:hidden}}
    .prod-badge{{position:absolute;top:10px;left:10px;font-size:12px;font-weight:700;padding:4px 10px;border-radius:999px;
      background:linear-gradient(120deg,var(--accent),var(--grad2));color:#fff}}
    .prod .price-tag{{margin:2px 0 0}}
    .prod-row{{display:flex;align-items:center;margin:12px 0 14px}}
    .prod .btn{{width:100%;padding:11px 20px;font-size:14.5px}}

    /* ---------- cart ---------- */
    .cart-fab{{position:fixed;right:22px;bottom:22px;z-index:60;width:60px;height:60px;border-radius:50%;border:none;cursor:pointer;
      background:linear-gradient(120deg,var(--accent),var(--grad2));color:#fff;display:flex;align-items:center;justify-content:center;
      box-shadow:0 14px 34px color-mix(in srgb,var(--accent) 45%,transparent);transition:transform .15s ease}}
    .cart-fab:hover{{transform:translateY(-2px)}}
    .cart-fab svg{{width:26px;height:26px}}
    .cart-fab.bump{{animation:bump .35s ease}}
    @keyframes bump{{40%{{transform:scale(1.18)}}}}
    .cart-count{{position:absolute;top:-4px;right:-4px;min-width:24px;height:24px;border-radius:99px;background:#ef4444;color:#fff;
      font-size:13px;font-weight:800;display:flex;align-items:center;justify-content:center;padding:0 6px;border:2px solid var(--bg)}}
    .cart-overlay{{position:fixed;inset:0;background:rgba(10,12,24,.45);z-index:70}}
    .cart-drawer{{position:fixed;top:0;right:-420px;width:min(400px,94vw);height:100vh;z-index:71;background:var(--surface);
      box-shadow:-20px 0 60px rgba(0,0,0,.25);display:flex;flex-direction:column;padding:22px;transition:right .28s ease;overflow-y:auto}}
    .cart-drawer.open{{right:0}}
    .cart-head{{display:flex;align-items:center;justify-content:space-between;font-size:19px;margin-bottom:16px}}
    .cart-close{{background:var(--surface2);border:1px solid var(--border);color:var(--muted);width:36px;height:36px;
      border-radius:10px;font-size:20px;cursor:pointer}}
    .cart-items{{display:grid;gap:12px}}
    .cart-item{{display:flex;align-items:center;gap:12px;background:var(--surface2);border:1px solid var(--border);
      border-radius:13px;padding:12px 14px}}
    .ci-name{{flex:1;font-weight:600;font-size:14.5px;line-height:1.35}}
    .ci-name small{{display:block;color:var(--muted);font-weight:500;margin-top:2px}}
    .ci-qty{{display:flex;align-items:center;gap:9px}}
    .ci-qty button{{width:28px;height:28px;border-radius:8px;border:1px solid var(--border);background:var(--surface);
      color:var(--text);font-size:16px;cursor:pointer;line-height:1}}
    .ci-qty span{{min-width:18px;text-align:center;font-weight:700}}
    .ci-sum{{font-weight:700;font-size:14px;color:var(--accent);min-width:74px;text-align:right}}
    .cart-total{{margin-top:16px;font-size:16px;display:flex;justify-content:space-between;border-top:1px solid var(--border);padding-top:14px}}
    .cart-total b{{font-size:19px;color:var(--accent)}}
    .cart-form{{margin-top:16px;box-shadow:none;border:1px solid var(--border)}}
    .cart-empty,.cart-ok{{margin:auto;text-align:center;color:var(--muted);font-size:15px;padding:30px 10px}}
    .cart-ok{{color:var(--accent);font-weight:700}}
    .cart-empty a{{color:var(--accent)}}

    /* ---------- footer ---------- */
    .ftr{{border-top:1px solid var(--border);padding:34px 0;font-size:14px;color:var(--muted)}}
    .ftr-in{{display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between}}

    @media(max-width:900px){{
      .hero-grid,.about-grid,.contact-card{{grid-template-columns:1fr}}
      .grid.c3{{grid-template-columns:repeat(2,1fr)}}
      .hero{{padding:64px 0}}
      .hero-art{{min-height:280px}}
      .nav{{display:none}}
      .burger{{display:block}}
      .nav.open{{display:flex;position:absolute;top:68px;left:0;right:0;flex-direction:column;
        background:var(--bg);border-bottom:1px solid var(--border);padding:18px 24px;gap:14px}}
      .hdr .btn{{display:none}}
      .section{{padding:60px 0}}
      .contact-card{{padding:32px}}
      .stats{{grid-template-columns:1fr 1fr}}
    }}
    @media(max-width:560px){{
      .grid.c3,.grid.c2{{grid-template-columns:1fr}}
      .hero-cta .btn{{width:100%}}
    }}
    """
