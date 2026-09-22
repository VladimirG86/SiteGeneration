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
