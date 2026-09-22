import json
from unittest.mock import Mock, patch
import importer

def test_validate_url_normalizes_and_blocks():
    assert importer.validate_url("example.com") == "https://example.com"
    assert importer.validate_url("https://example.com/path#frag") == "https://example.com/path"
    # SSRF
    import pytest
    with pytest.raises(ValueError):
        importer.validate_url("http://127.0.0.1")
    with pytest.raises(ValueError):
        importer.validate_url("http://10.0.0.5")
    with pytest.raises(ValueError):
        importer.validate_url("ftp://example.com")
    with pytest.raises(ValueError):
        importer.validate_url("http://test.local")

def test_extract_signals_basic():
    html = """<html><head><title>My Shop</title><meta name="description" content="desc here"></head>
    <body><h1>Big Title</h1><h2>Service A</h2><p>Text A 120 ₽</p><p>+7 (900) 111-22-33</p><p>hi@test.ru</p><a href="/about">О нас</a></body></html>"""
    s = importer.extract_signals(html, "https://example.com/page")
    assert s["title"] == "My Shop"
    assert s["h1"] == ["Big Title"]
    assert "+7 (900) 111-22-33" in s["phones"]
    assert "hi@test.ru" in s["emails"]
    assert any("about" in x["href"] for x in s["nav"])

def test_heuristic_site_structure():
    import chat as chat_ops
    signals = {
        "url": "https://example.com",
        "title": "Bakery Test",
        "description": "Хлеб в Казани",
        "h1": ["Пекарня — свежий хлеб"],
        "h2": ["Услуги", "Доставка"],
        "h3": [],
        "paragraphs": ["Хлеб на закваске — 120 ₽", "Доставим за час"],
        "phones": ["+7 (843) 111-22-33"],
        "emails": ["a@b.ru"],
    }
    site = importer.heuristic_site(signals, "light", "blue")
    # должен пройти нормализацию
    site = chat_ops.normalize_site(site)
    assert site["brand"] == "Bakery Test"
    assert site["phone"] == "+7 (843) 111-22-33"
    assert any(sec["type"] == "hero" for sec in site["sections"])
    assert any(sec["type"] == "services" for sec in site["sections"])

def test_pick_accent():
    assert importer.pick_accent_from_colors(["#2563eb", "#ffffff"]) == "blue"
    assert importer.pick_accent_from_colors(["#ea580c"]) == "orange"
    assert importer.pick_accent_from_colors(["#cccccc", "#eeeeee"]) is None
    assert importer.pick_accent_from_colors([]) is None


def test_heuristic_shop_detection():
    html = """<html><head><title>Shop Test</title></head><body>
    <h1>Магазин Товары</h1><h2>Каталог</h2>
    <p>Товар A — 1200 ₽</p><p>Товар B — 2300 ₽</p><p>Товар C — 999 ₽</p>
    <p>Купить доставка каталог товары магазин цена цены</p>
    </body></html>"""
    sig = importer.extract_signals(html, "https://shop.example.com")
    site = importer.heuristic_site(sig, "light", "purple")
    # должен стать магазином с каталогом и корзиной
    assert any(s["type"] == "products" for s in site["sections"])
    assert site["features"]["cart"] is True
    assert any(s.get("id") == "catalog" or s["type"] == "products" for s in site["sections"])


def test_wp_publish_with_media(client, tmp_path, monkeypatch):
    import app as appmod
    import images, generator, chat as chat_ops, demo_content, sections
    import httpx as _httpx
    import json as _json
    monkeypatch.setattr(images, "ASSETS_DIR", str(tmp_path / "assets"))
    # создаём сайт с hero
    site = chat_ops.normalize_site(demo_content.build_site(
        {"Название": "T", "О бизнесе": "Кафе в Казани.", "Услуги/товары": "Кофе - 100",
         "Преимущества": "Вкусно", "Дополнительно": ""}, "light", "blue"))
    site["theme"] = {"mode": "light", "accent": "blue"}
    from PIL import Image
    import io
    im = Image.new("RGB", (200, 200), color="blue")
    buf = io.BytesIO()
    im.save(buf, format="WEBP")
    webp = buf.getvalue()
    images._save_asset("wptest", "hero.webp", webp)
    site["hero_image"] = True
    generator._save_all("wptest", site, sections.render_page(dict(site), site_id="wptest"), True)
    from unittest.mock import Mock
    appmod._RATE.clear()
    orig_client = _httpx.Client
    media_resp = Mock()
    media_resp.status_code = 200
    media_resp.raise_for_status = lambda: None
    media_resp.json = lambda: {"id": 99, "source_url": "https://wp.example.com/wp-content/uploads/hero.webp"}
    page_resp = Mock()
    page_resp.status_code = 201
    page_resp.raise_for_status = lambda: None
    page_resp.json = lambda: {"id": 123, "link": "https://wp.example.com/page"}
    calls = []
    def _fake_post(self, url, **kw):
        calls.append(url)
        if "/wp-json/wp/v2/media" in url:
            return media_resp
        return page_resp
    def _fake_client(*args, **kwargs):
        # TestClient использует base_url=http://testserver — пропускаем
        if kwargs.get("base_url", "").startswith("http://testserver") or "app" in kwargs:
            return orig_client(*args, **kwargs)
        m = Mock()
        m.__enter__ = lambda s: m
        m.__exit__ = lambda *a: False
        m.post = lambda url, **kw: _fake_post(m, url, **kw)
        return m
    monkeypatch.setattr(_httpx, "Client", _fake_client)
    r = client.post("/api/publish/wp/wptest", json={"wp_url": "https://wp.example.com", "username": "admin", "app_password": "app-pass"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["featured_media"] == 99
    assert any("/media" in c for c in calls)
    assert any("/pages" in c for c in calls)


def test_try_attach_images(tmp_path, monkeypatch):
    import images
    # перенаправляем assets в tmp
    monkeypatch.setattr(images, "ASSETS_DIR", str(tmp_path / "assets"))
    # поддельная картинка 900x600 png -> webp (шумная чтобы пройти фильтр 5к)
    from PIL import Image
    import io, os
    import random
    random.seed(0)
    im = Image.new("RGB", (900, 600))
    pix = im.load()
    for x in range(900):
        for y in range(600):
            pix[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    monkeypatch.setattr(importer, "_download_image_bytes", lambda url, **k: png_bytes)
    site = {"brand": "Test"}
    signals = {"images": ["https://example.com/a.jpg"]}
    ok = importer.try_attach_original_images(site, signals, "job123")
    assert ok is True
    assert site.get("hero_image") is True
    # файл должен появиться
    import os
    assert os.path.exists(os.path.join(str(tmp_path / "assets"), "job123", "hero.webp"))


def test_import_api_mocked(client, tmp_path, monkeypatch):
    html = """<html><head><title>Site Imported</title></head><body><h1>Заголовок импорта</h1><p>+7 (900) 222-33-44</p><style>.a{color:#2563eb}</style></body></html>"""
    import app as appmod
    appmod._RATE.clear()
    import llm
    monkeypatch.setattr(importer, "fetch_html", lambda url: (html, "https://example.com"))
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    r = client.post("/api/import", json={"url": "https://example.com"})
    assert r.status_code == 200, r.text
    job = r.json()["job_id"]
    # дождаться окончания
    import time
    for _ in range(30):
        jr = client.get(f"/api/job/{job}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    # автопалитра должна была подобрать blue (#2563eb близко к blue accent)
    import generator
    site = generator.get_site_dict(job)
    assert site["theme"]["accent"] == "blue"
    assert site["import_source"] == "https://example.com"
    # экспорт
    rz = client.get(f"/api/export/{job}")
    assert rz.status_code == 200
    assert rz.headers["content-type"] == "application/zip"
    # чат-правка на импортированном сайте
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps({"reply":"ok","ops":[{"op":"set_theme","mode":"dark"}]}))
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    appmod._RATE.clear()
    rc = client.post(f"/api/chat/{job}", json={"message": "сделай тёмную тему"})
    assert rc.status_code == 200
    assert rc.json()["applied"] == 1
