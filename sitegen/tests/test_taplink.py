import json, time
import demo_content, sections, chat, generator, llm, app as appmod

def test_taplink_demo():
    site = demo_content.build_taplink_site(
        {"Название": "Иван Петров", "О бизнесе": "Фотограф в Казани", "Услуги/товары": "Портфолио - https://ivan.example.com\nЗапись - https://t.me/ivan", "Дополнительно": "Пишите"},
        "light", "blue")
    assert site["kind"] == "taplink"
    assert any(s["type"] == "profile" for s in site["sections"])
    assert any(s["type"] == "tap_links" for s in site["sections"])
    # normalize
    site = chat.normalize_site(site)
    assert site["kind"] == "taplink"
    html = sections.render_page(site, site_id="testtap")
    assert "tap-link" in html
    assert "tap-profile" in html

def test_vcard_demo():
    site = demo_content.build_vcard_site(
        {"Название": "Анна", "О бизнесе": "Дизайнер", "Должность": "Арт-директор", "Компания": "Студия Свет", "Дополнительно": "Москва"},
        "light", "rose")
    assert site["kind"] == "vcard"
    assert any(s["type"] == "qrcode" for s in site["sections"])
    site = chat.normalize_site(site)
    assert site["kind"] == "vcard"
    html = sections.render_page(site, site_id="testvcard")
    assert "qr-img" in html
    assert "vcard-contact" in html

def test_sanitize_new_types():
    # profile requires name or bio
    assert chat.sanitize_section({"type": "profile", "name": "Иван", "bio": "привет"}) is not None
    assert chat.sanitize_section({"type": "profile"}) is None
    # tap_links requires items
    assert chat.sanitize_section({"type": "tap_links", "items": [{"title": "Site", "url": "https://example.com"}]}) is not None
    assert chat.sanitize_section({"type": "tap_links", "items": []}) is None
    # socials
    assert chat.sanitize_section({"type": "socials", "items": [{"platform": "instagram", "url": "https://instagram.com/x"}]}) is not None
    # qrcode defaults
    q = chat.sanitize_section({"type": "qrcode", "title": "QR"})
    assert q is not None and "data" in q
    # vcard
    assert chat.sanitize_section({"type": "vcard", "items": [{"label": "Тел", "value": "+7"}]}) is not None
    # tap_text
    assert chat.sanitize_section({"type": "tap_text", "text": "hello"}) is not None
    assert chat.sanitize_section({"type": "tap_text"}) is None

def test_generate_taplink_api(client, tmp_path, monkeypatch):
    # force demo mode
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    appmod._RATE.clear()
    r = client.post("/api/generate", json={"name": "Иван Петров", "about": "Фотограф в Казани, снимаю свадьбы и портреты", "products": "Портфолио - https://example.com\nЗапись - https://t.me/ivan", "advantages": "", "extras": "", "theme_mode": "light", "accent": "blue", "email": "a@b.ru", "kind": "taplink"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    assert r.json()["kind"] == "taplink"
    for _ in range(30):
        jr = client.get(f"/api/job/{jid}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    site = generator.get_site_dict(jid)
    assert site["kind"] == "taplink"
    assert any(s["type"] == "tap_links" for s in site["sections"])
    html = generator.get_site_html(jid)
    assert "tap-link" in html

def test_generate_vcard_api(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    appmod._RATE.clear()
    r = client.post("/api/generate", json={"name": "Анна Смирнова", "about": "Арт-директор в Студии Свет", "products": "", "advantages": "", "extras": "Москва, ул. Тверская", "theme_mode": "light", "accent": "rose", "email": "b@c.ru", "kind": "vcard"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    assert r.json()["kind"] == "vcard"
    for _ in range(30):
        jr = client.get(f"/api/job/{jid}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    site = generator.get_site_dict(jid)
    assert site["kind"] == "vcard"
    assert any(s["type"] == "qrcode" for s in site["sections"])
    html = generator.get_site_html(jid)
    assert "qr-img" in html

def test_chat_edit_taplink(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    appmod._RATE.clear()
    r = client.post("/api/generate", json={"name": "Test", "about": "Тест taplink для редактирования ссылок", "products": "Link1 - https://a.com", "advantages": "", "extras": "", "theme_mode": "light", "accent": "purple", "email": "c@d.ru", "kind": "taplink"})
    jid = r.json()["job_id"]
    for _ in range(30):
        jr = client.get(f"/api/job/{jid}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    # теперь чат-правка: добавляем ссылку
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps({"reply": "Добавил ссылку", "ops": [{"op": "upsert_section", "section": {"type": "tap_links", "title": "Обновлённые ссылки", "items": [{"title": "Новый линк", "url": "https://new.example.com", "icon": "⭐"}]}}]}))
    appmod._RATE.clear()
    rc = client.post(f"/api/chat/{jid}", json={"message": "добавь ссылку на новый проект"})
    assert rc.status_code == 200, rc.text
    data = rc.json()
    assert data["applied"] == 1
    site = generator.get_site_dict(jid)
    # проверяем что секция обновилась
    links_secs = [s for s in site["sections"] if s["type"] == "tap_links"]
    assert links_secs and any("Новый линк" in str(s) for s in links_secs)

def test_default_kind_landing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    appmod._RATE.clear()
    r = client.post("/api/generate", json={"name": "Comp", "about": "Компания в Москве делает ремонт", "products": "Услуга 1\nУслуга 2", "advantages": "", "extras": "", "theme_mode": "light", "accent": "purple", "email": "e@f.ru"})
    assert r.status_code == 200
    assert r.json().get("kind", "landing") == "landing"
    jid = r.json()["job_id"]
    for _ in range(30):
        jr = client.get(f"/api/job/{jid}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    site = generator.get_site_dict(jid)
    assert site.get("kind", "landing") == "landing"
