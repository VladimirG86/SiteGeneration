"""Дизайн-система сгенерированных сайтов.

Идея (как у VERSTKA.ai): не «ИИ рисует что попало», а контролируемые
токены темы × библиотека секций. Модель управляет контентом и выбором
темы, вёрстка детерминирована — результат всегда аккуратный.
Применён бренд-борд Nelvi: палитра indigo/coral/mint, шрифты Unbounded + Inter,
скругления 10–16px, дружелюбный тон.
"""

ACCENTS = {
    # Nelvi — бренд-борд: indigo/coral/mint как три ключевых, остальные — производные для совместимости
    "purple":  {"label": "Индиго",   "main": "#5B5FEF", "dark": "#4A4DD1", "soft": "#EDEFFF", "grad": "#7B7FFF"},
    "blue":    {"label": "Вуаль",    "main": "#7B7FFF", "dark": "#6366F1", "soft": "#EDEFFF", "grad": "#5B5FEF"},
    "emerald": {"label": "Минт",     "main": "#2EC4B6", "dark": "#1FA99B", "soft": "#E6FBF9", "grad": "#3EDBC9"},
    "orange":  {"label": "Коралл",   "main": "#FF7A59", "dark": "#E86647", "soft": "#FFF0EB", "grad": "#FF9A7A"},
    "rose":    {"label": "Персик",   "main": "#FF9A7A", "dark": "#FF7A59", "soft": "#FFF0EB", "grad": "#FF7A59"},
    "teal":    {"label": "Графит",   "main": "#2B2B36", "dark": "#1B1B24", "soft": "#E7E5F0", "grad": "#5B5FEF"},
}

MODES = ("light", "dark")

FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@400;600;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
)


def build_css(mode: str, accent: str) -> str:
    a = ACCENTS.get(accent, ACCENTS["purple"])
    if mode == "dark":
        vars_ = f"""
      --bg:#1B1B24; --bg2:#1B1B24; --surface:#24242F; --surface2:#2C2C38;
      --text:#F3F2F8; --muted:#A9A8B5; --border:#34343F;
      --shadow:0 18px 50px rgba(0,0,0,.35);
      --accent:{a['main']}; --accent-dark:{a['dark']}; --accent-soft:color-mix(in srgb,{a['main']} 18%,transparent);
      --accent-soft2:{a['soft']}; --grad2:{a['grad']};
      --hero-glow:radial-gradient(700px 340px at 75% -10%, {a['main']}22, transparent 70%);
    """
    else:
        vars_ = f"""
      --bg:#FAF9F7; --bg2:#FAF9F7; --surface:#FFFFFF; --surface2:#F3F2F8;
      --text:#2B2B36; --muted:#7A7A8E; --border:#E7E5F0;
      --shadow:0 18px 50px rgba(43,43,54,.08);
      --accent:{a['main']}; --accent-dark:{a['dark']}; --accent-soft:{a['soft']};
      --accent-soft2:{a['soft']}; --grad2:{a['grad']};
      --hero-glow:radial-gradient(700px 340px at 75% -10%, {a['main']}14, transparent 70%);
    """
    return f"""
    :root{{{vars_}}}
    *{{margin:0;padding:0;box-sizing:border-box}}
    html{{-webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale}}
    html{{scroll-behavior:smooth; scrollbar-gutter:stable}}
    ::selection{{background:var(--accent); color:#fff}}
    :focus-visible{{outline:2px solid var(--accent); outline-offset:2px}}
    @media (prefers-reduced-motion: reduce){{ *,*::before,*::after{{animation-duration:.01ms!important; transition-duration:.01ms!important; scroll-behavior:auto!important}}}}
    body{{font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;
      background:var(--bg);color:var(--text);line-height:1.6;font-size:16px}}
    img,svg{{display:block;max-width:100%}}
    a{{color:inherit;text-decoration:none}}
    .wrap{{max-width:1120px;margin:0 auto;padding:0 24px}}

    /* ---------- header ---------- */
    .hdr{{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--bg) 84%,transparent);
      backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}}
    .hdr-in{{display:flex;align-items:center;gap:28px;height:64px}}
    .logo{{display:flex;align-items:center;gap:10px;font-family:'Unbounded',sans-serif;font-weight:800;font-size:18px;letter-spacing:-.4px}}
    .logo-mark{{width:36px;height:36px;border-radius:10px;flex:0 0 auto;
      background:linear-gradient(135deg,var(--accent),var(--grad2));color:#fff;
      display:flex;align-items:center;justify-content:center;box-shadow:0 6px 14px color-mix(in srgb,var(--accent) 28%,transparent)}}
    .logo-mark svg{{width:20px;height:20px}}
    .nav{{display:flex;gap:22px;margin-left:auto;font-size:14px;font-weight:500;color:var(--muted);font-family:'Inter',sans-serif}}
    .nav a{{transition:color .14s ease}}
    .nav a:hover{{color:var(--accent)}}
    .hdr .btn{{margin-left:8px}}
    .burger{{display:none;margin-left:auto;background:none;border:1px solid var(--border);
      border-radius:10px;padding:8px 10px;color:var(--text);font-size:16px;cursor:pointer}}

    /* ---------- buttons — Nelvi: 10px radius, Inter 600 ---------- */
    .btn{{display:inline-flex;align-items:center;justify-content:center;gap:8px;
      padding:11px 20px;border-radius:10px;font-family:'Inter',sans-serif;font-weight:600;font-size:14px;cursor:pointer;
      border:none;color:#fff;background:var(--accent);
      box-shadow:0 6px 16px color-mix(in srgb,var(--accent) 28%,transparent);
      transition:transform .14s ease,box-shadow .14s ease,background .14s ease}}
    .btn:hover{{transform:translateY(-1px);box-shadow:0 10px 22px color-mix(in srgb,var(--accent) 34%,transparent)}}
    .btn:active{{transform:translateY(0)}}
    .btn.ghost{{background:transparent;color:var(--accent);border:1.5px solid var(--accent);box-shadow:none}}
    .btn.ghost:hover{{background:var(--accent);color:#fff;transform:none}}
    /* coral CTA variant — используется как .btn-accent */
    .btn-accent{{background:#FF7A59;color:#fff}}
    .btn-accent:hover{{background:#E86647}}

    /* ---------- sections ---------- */
    .section{{padding:80px 0}}
    .section.alt{{background:var(--bg2)}}
    .kicker{{display:inline-flex;align-items:center;gap:8px;font-family:'Inter',sans-serif;font-size:12px;font-weight:600;
      letter-spacing:.06em;text-transform:uppercase;color:var(--accent);
      background:var(--accent-soft);padding:6px 12px;border-radius:999px;margin-bottom:16px}}
    h1{{font-family:'Unbounded',sans-serif;font-size:clamp(30px,4.6vw,48px);line-height:1.08;letter-spacing:-.04em;font-weight:800}}
    h2{{font-family:'Unbounded',sans-serif;font-size:clamp(22px,3.2vw,34px);line-height:1.18;letter-spacing:-.03em;font-weight:600;margin-bottom:14px}}
    h3{{font-family:'Unbounded',sans-serif;font-weight:600}}
    .lead{{color:var(--muted);font-family:'Inter',sans-serif;font-size:16px;max-width:640px;line-height:1.6}}

    /* ---------- hero ---------- */
    .hero{{position:relative;padding:88px 0 84px;overflow:hidden;background:var(--hero-glow); isolation:isolate}}
    .hero-grid{{display:grid;grid-template-columns:1.15fr .85fr;gap:56px;align-items:center}}
    .hero .lead{{margin:18px 0 28px;font-size:17px}}
    .hero-cta{{display:flex;gap:12px;flex-wrap:wrap}}
    .badges{{display:flex;flex-wrap:wrap;gap:10px;margin-top:28px}}
    .badge{{font-family:'Inter',sans-serif;font-size:13px;font-weight:600;padding:7px 12px;border-radius:999px;
      background:var(--accent-soft);color:var(--accent-dark);border:1px solid color-mix(in srgb,var(--accent) 18%,transparent)}}
    .stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:40px}}
    .stat{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:18px 20px;box-shadow:var(--shadow)}}
    .stat b{{display:block;font-family:'Unbounded',sans-serif;font-size:24px;letter-spacing:-.02em;color:var(--accent)}}
    .stat span{{font-size:13px;color:var(--muted);font-family:'Inter',sans-serif}}
    .hero-art{{position:relative;border-radius:24px;min-height:380px;overflow:hidden;
      background:linear-gradient(135deg,var(--accent),var(--grad2));box-shadow:var(--shadow)}}
    .hero-photo{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
    .prod-photo{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
    .hero-art svg{{position:absolute;inset:0;width:100%;height:100%}}
    .hero-card{{position:absolute;left:20px;right:20px;bottom:20px;background:var(--surface);
      border-radius:16px;padding:16px 18px;box-shadow:var(--shadow);font-size:14px;font-family:'Inter',sans-serif}}
    .hero-card b{{color:var(--accent)}}

    /* ---------- grids & cards ---------- */
    .grid{{display:grid;gap:18px;margin-top:36px}}
    .grid.c3{{grid-template-columns:repeat(3,1fr)}}
    .grid.c2{{grid-template-columns:repeat(2,1fr)}}
    .card{{background:var(--surface);border:1px solid var(--border);border-radius:16px;
      padding:24px;transition:transform .14s ease,box-shadow .14s ease}}
    .card:hover{{transform:translateY(-2px);box-shadow:var(--shadow)}}
    .card h3{{font-family:'Unbounded',sans-serif;font-size:17px;font-weight:600;margin:14px 0 8px;letter-spacing:-.02em}}
    .card p{{color:var(--muted);font-family:'Inter',sans-serif;font-size:14px;line-height:1.6}}
    .price-tag{{display:inline-block;margin-top:12px;font-family:'Inter',sans-serif;font-weight:700;font-size:15px;color:var(--accent)}}
    .icon{{width:46px;height:46px;border-radius:13px;background:var(--accent-soft);color:var(--accent);
      display:flex;align-items:center;justify-content:center}}
    .icon svg{{width:22px;height:22px;stroke:var(--accent);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}
    .check-item{{display:flex;gap:12px;align-items:flex-start}}
    .check-item .icon{{flex:0 0 auto;width:38px;height:38px;border-radius:11px}}
    .check-item h3{{margin:2px 0 4px}}

    /* ---------- about ---------- */
    .about-grid{{display:grid;grid-template-columns:1fr 1fr;gap:44px;align-items:start;margin-top:8px}}
    .about-grid .paragraphs p{{color:var(--muted);margin-bottom:12px;font-family:'Inter',sans-serif}}
    .bullets{{display:grid;gap:12px}}
    .bullet{{display:flex;gap:12px;align-items:flex-start;background:var(--surface);
      border:1px solid var(--border);border-radius:14px;padding:14px 18px;font-family:'Inter',sans-serif;font-weight:600;font-size:14px}}
    .bullet svg{{width:20px;height:20px;color:var(--accent);flex:0 0 auto;margin-top:2px;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}

    /* ---------- process ---------- */
    .steps{{counter-reset:step;display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px;margin-top:36px}}
    .step{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:22px;position:relative}}
    .step::before{{counter-increment:step;content:counter(step);width:36px;height:36px;border-radius:10px;
      display:flex;align-items:center;justify-content:center;font-family:'Unbounded',sans-serif;font-weight:800;font-size:15px;color:#fff;
      background:var(--accent);margin-bottom:12px}}
    .step h3{{font-family:'Unbounded',sans-serif;font-size:15.5px;margin-bottom:6px}}
    .step p{{color:var(--muted);font-family:'Inter',sans-serif;font-size:13.5px;line-height:1.6}}

    /* ---------- prices ---------- */
    .price-card{{display:flex;flex-direction:column;border-radius:16px}}
    .price-card .price{{font-family:'Unbounded',sans-serif;font-size:26px;font-weight:800;letter-spacing:-.02em;color:var(--accent);margin:10px 0 4px}}
    .price-card ul{{list-style:none;margin:14px 0 20px;display:grid;gap:9px}}
    .price-card li{{display:flex;gap:9px;color:var(--muted);font-family:'Inter',sans-serif;font-size:14px}}
    .price-card li svg{{width:18px;height:18px;color:var(--accent);flex:0 0 auto;margin-top:3px;stroke-width:2}}
    .price-card .btn{{margin-top:auto}}
    .price-card.featured{{border:1.5px solid var(--accent);position:relative}}
    .price-card.featured::after{{content:'Популярный';position:absolute;top:-11px;left:20px;
      background:var(--accent);color:#fff;font-family:'Inter',sans-serif;font-size:11px;
      font-weight:700;padding:4px 10px;border-radius:999px}}
    .price-note{{text-align:center;color:var(--muted);font-family:'Inter',sans-serif;font-size:13px;margin-top:20px}}

    /* ---------- reviews ---------- */
    .review-stars{{color:#FF9A7A;letter-spacing:2px;font-size:15px}}
    .review-meta{{margin-top:10px;font-size:13px;color:var(--muted);font-weight:600;font-family:'Inter',sans-serif}}
    .review-name{{display:flex;align-items:center;gap:10px;margin-top:14px;font-family:'Inter',sans-serif;font-weight:700;font-size:14px}}
    .avatar{{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,var(--accent),var(--grad2));
      color:#fff;display:flex;align-items:center;justify-content:center;font-family:'Unbounded',sans-serif;font-weight:800;font-size:14px}}

    /* ---------- faq ---------- */
    .faq-list{{max-width:760px;margin:36px auto 0;display:grid;gap:12px}}
    .faq-list details{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:18px 22px}}
    .faq-list summary{{cursor:pointer;font-family:'Unbounded',sans-serif;font-weight:600;font-size:15px;list-style:none;display:flex;justify-content:space-between;gap:16px;align-items:center}}
    .faq-list summary::-webkit-details-marker{{display:none}}
    .faq-list summary::after{{content:'+';font-size:22px;color:var(--accent);font-weight:600;line-height:1}}
    .faq-list details[open] summary::after{{content:'–'}}
    .faq-list details p{{color:var(--muted);margin-top:12px;font-family:'Inter',sans-serif;font-size:14px;line-height:1.6}}

    /* ---------- contacts — Nelvi gradient ---------- */
    .contact-card{{background:linear-gradient(135deg,var(--accent),var(--grad2));border-radius:24px;
      padding:48px;display:grid;grid-template-columns:1fr 1fr;gap:40px;color:#fff;box-shadow:var(--shadow)}}
    .contact-card h2{{color:#fff;font-family:'Unbounded',sans-serif}}
    .contact-card .lead{{color:rgba(255,255,255,.9);font-family:'Inter',sans-serif}}
    .contact-info{{display:grid;gap:10px;margin-top:24px;font-family:'Inter',sans-serif;font-size:14px}}
    .contact-info div{{display:flex;gap:10px;align-items:center}}
    .form{{background:var(--surface);border-radius:16px;padding:24px;display:grid;gap:14px;box-shadow:var(--shadow)}}
    .form label{{font-family:'Inter',sans-serif;font-size:13px;font-weight:600;color:var(--text);display:grid;gap:6px}}
    .form input,.form textarea{{border:1.5px solid var(--border);background:var(--surface2);color:var(--text);
      border-radius:10px;padding:11px 14px;font:inherit;font-family:'Inter',sans-serif;font-size:14px;outline:none;width:100%}}
    .form input:focus,.form textarea:focus{{border-color:var(--accent)}}
    .form .btn{{width:100%;border-radius:10px}}
    .form-ok{{display:none;text-align:center;color:#2EC4B6;font-family:'Inter',sans-serif;font-weight:700;padding:28px 10px}}

    /* ---------- products / shop ---------- */
    .prod{{display:flex;flex-direction:column;border-radius:16px}}
    .prod-img{{position:relative;height:150px;border-radius:14px;display:flex;align-items:center;justify-content:center;
      font-size:54px;background:linear-gradient(135deg,var(--accent-soft),color-mix(in srgb,var(--accent) 14%,var(--bg2)));overflow:hidden}}
    .prod-badge{{position:absolute;top:10px;left:10px;font-family:'Inter',sans-serif;font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px;
      background:var(--accent);color:#fff}}
    .prod .price-tag{{margin:2px 0 0}}
    .prod-row{{display:flex;align-items:center;margin:12px 0 14px}}
    .prod .btn{{width:100%;padding:10px 20px;font-size:14px;border-radius:10px}}

    /* ---------- vcard (QR + ссылки) — Nelvi 520px center ---------- */
    .tap-page{{background:var(--bg);min-height:100vh}}
    .tap-wrap{{max-width:520px;margin:0 auto;padding:28px 18px 40px}}
    .tap-profile{{text-align:center;padding:28px 20px 10px}}
    .tap-avatar{{width:96px;height:96px;border-radius:22px;margin:0 auto 14px;overflow:hidden;background:linear-gradient(135deg,var(--accent),var(--grad2));display:flex;align-items:center;justify-content:center;color:#fff;font-family:'Unbounded',sans-serif;font-weight:800;font-size:36px;position:relative;box-shadow:0 6px 18px color-mix(in srgb,var(--accent) 30%,transparent)}}
    .tap-avatar img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
    .tap-name{{font-family:'Unbounded',sans-serif;font-size:22px;font-weight:800;letter-spacing:-.03em;margin-bottom:6px}}
    .tap-subtitle{{font-family:'Inter',sans-serif;font-size:14px;color:var(--muted);margin-bottom:10px}}
    .tap-bio{{font-family:'Inter',sans-serif;font-size:14px;color:var(--muted);line-height:1.6;max-width:420px;margin:0 auto}}
    .tap-badges{{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:14px}}
    .tap-badges span{{font-family:'Inter',sans-serif;font-size:12px;font-weight:700;padding:5px 10px;border-radius:999px;background:var(--accent-soft);color:var(--accent-dark)}}
    .tap-links{{display:grid;gap:12px;margin-top:22px}}
    .tap-link{{display:flex;align-items:center;gap:14px;padding:16px 18px;border-radius:14px;border:1px solid var(--border);background:var(--surface);box-shadow:0 6px 18px rgba(43,43,54,.06);transition:transform .13s ease,box-shadow .13s}}
    .tap-link.filled{{background:var(--accent);color:#fff;border-color:transparent;box-shadow:0 8px 18px color-mix(in srgb,var(--accent) 28%,transparent)}}
    .tap-link:hover{{transform:translateY(-1px);box-shadow:0 10px 24px rgba(43,43,54,.10)}}
    .tap-link-ico{{width:42px;height:42px;border-radius:10px;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:20px;flex:0 0 auto}}
    .tap-link.filled .tap-link-ico{{background:rgba(255,255,255,.22);color:#fff}}
    .tap-link-title{{font-family:'Unbounded',sans-serif;font-weight:600;font-size:14.5px;letter-spacing:-.01em}}
    .tap-link-sub{{font-family:'Inter',sans-serif;font-size:12.5px;opacity:.8;margin-top:2px}}
    .tap-link-arrow{{margin-left:auto;opacity:.5}}
    .socials{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:18px}}
    .social-btn{{width:52px;height:52px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--surface);border:1px solid var(--border);color:var(--text);font-size:20px;box-shadow:0 4px 14px rgba(43,43,54,.06);transition:transform .12s}}
    .social-btn:hover{{transform:translateY(-1px);border-color:var(--accent);color:var(--accent)}}
    .messengers{{display:grid;gap:10px;margin-top:18px}}
    .msgr-btn{{display:flex;align-items:center;gap:12px;padding:14px 18px;border-radius:14px;background:var(--surface);border:1px solid var(--border);font-family:'Inter',sans-serif;font-weight:600}}
    .msgr-btn.wa{{background:#25D366;color:#fff;border-color:transparent}}
    .msgr-btn.tg{{background:#2AABEE;color:#fff;border-color:transparent}}
    .msgr-btn.vb{{background:#7360F2;color:#fff;border-color:transparent}}
    .qr-card{{text-align:center;margin-top:24px;padding:24px;background:var(--surface);border:1px solid var(--border);border-radius:18px;box-shadow:var(--shadow)}}
    .qr-img{{width:220px;height:220px;margin:14px auto;background:#fff;border-radius:14px;padding:10px;box-shadow:0 6px 18px rgba(43,43,54,.08)}}
    .qr-img img{{width:100%;height:100%;object-fit:contain}}
    .vcard-actions{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:16px}}
    .vcard-contact{{display:flex;align-items:center;gap:12px;padding:14px 16px;border-radius:14px;background:var(--surface2);border:1px solid var(--border);margin-top:10px}}
    .vcard-contact .ic{{width:40px;height:40px;border-radius:10px;background:var(--accent-soft);color:var(--accent);display:flex;align-items:center;justify-content:center}}
    .vcard-contact .ic svg{{stroke:var(--accent);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}
    .tap-text{{margin-top:20px;padding:18px;background:var(--surface);border:1px solid var(--border);border-radius:14px;color:var(--muted);font-family:'Inter',sans-serif;font-size:14px;line-height:1.6}}
    .tap-text h3{{font-family:'Unbounded',sans-serif}}

    /* ---------- cart — Nelvi mint success ---------- */
    .cart-fab{{position:fixed;right:22px;bottom:22px;z-index:60;width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;
      background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;
      box-shadow:0 10px 28px color-mix(in srgb,var(--accent) 36%,transparent);transition:transform .14s ease}}
    .cart-fab:hover{{transform:translateY(-1px)}}
    .cart-fab svg{{width:24px;height:24px;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}}
    .cart-fab.bump{{animation:bump .35s ease}}
    @keyframes bump{{40%{{transform:scale(1.14)}}}}
    .cart-count{{position:absolute;top:-4px;right:-4px;min-width:22px;height:22px;border-radius:99px;background:#FF7A59;color:#fff;
      font-family:'Inter',sans-serif;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;padding:0 6px;border:2px solid var(--bg)}}
    .cart-overlay{{position:fixed;inset:0;background:rgba(27,27,36,.45);z-index:70}}
    .cart-drawer{{position:fixed;top:0;right:-420px;width:min(400px,94vw);height:100vh;z-index:71;background:var(--surface);
      box-shadow:-20px 0 60px rgba(0,0,0,.22);display:flex;flex-direction:column;padding:22px;transition:right .28s ease;overflow-y:auto}}
    .cart-drawer.open{{right:0}}
    .cart-head{{display:flex;align-items:center;justify-content:space-between;font-family:'Unbounded',sans-serif;font-size:17px;margin-bottom:16px}}
    .cart-close{{background:var(--surface2);border:1px solid var(--border);color:var(--muted);width:36px;height:36px;
      border-radius:10px;font-size:20px;cursor:pointer;font-family:'Inter',sans-serif}}
    .cart-items{{display:grid;gap:12px}}
    .cart-item{{display:flex;align-items:center;gap:12px;background:var(--surface2);border:1px solid var(--border);
      border-radius:14px;padding:12px 14px}}
    .ci-name{{flex:1;font-family:'Inter',sans-serif;font-weight:600;font-size:14px;line-height:1.35}}
    .ci-name small{{display:block;color:var(--muted);font-weight:500;margin-top:2px}}
    .ci-qty{{display:flex;align-items:center;gap:9px}}
    .ci-qty button{{width:28px;height:28px;border-radius:8px;border:1px solid var(--border);background:var(--surface);
      color:var(--text);font-size:16px;cursor:pointer;line-height:1;font-family:'Inter',sans-serif}}
    .ci-qty span{{min-width:18px;text-align:center;font-weight:700;font-family:'Inter',sans-serif}}
    .ci-sum{{font-family:'Inter',sans-serif;font-weight:700;font-size:14px;color:var(--accent);min-width:74px;text-align:right}}
    .cart-total{{margin-top:16px;font-family:'Inter',sans-serif;font-size:15px;display:flex;justify-content:space-between;border-top:1px solid var(--border);padding-top:14px}}
    .cart-total b{{font-family:'Unbounded',sans-serif;font-size:17px;color:var(--accent)}}
    .cart-form{{margin-top:16px;box-shadow:none;border:1px solid var(--border);border-radius:16px}}
    .cart-empty,.cart-ok{{margin:auto;text-align:center;color:var(--muted);font-family:'Inter',sans-serif;font-size:14px;padding:30px 10px}}
    .cart-ok{{color:#2EC4B6;font-weight:700}}
    .cart-empty a{{color:var(--accent)}}

    /* ---------- toast — Nelvi mint ---------- */
    .toast{{display:flex;align-items:center;gap:10px;background:rgba(46,196,182,.12);border:1px solid #2EC4B6;color:#2EC4B6;padding:10px 14px;border-radius:10px;font-family:'Inter',sans-serif;font-size:13px;font-weight:600}}

    /* ---------- footer ---------- */
    .ftr{{border-top:1px solid var(--border);padding:30px 0;font-family:'Inter',sans-serif;font-size:13px;color:var(--muted)}}
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
