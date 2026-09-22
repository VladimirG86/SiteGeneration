import time, json, re
import generator, llm, app as appmod

def test_sitemap_and_robots(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    appmod._RATE.clear()
    r = client.post("/api/generate", json={"name": "Test Sitemap", "about": "Тест магазин в Казани с каталогом товаров", "products": "Товар A — 1000 ₽\nТовар B — 2000 ₽", "advantages": "", "extras": "", "theme_mode": "light", "accent": "blue", "email": "a@b.ru", "kind": "landing"})
    jid = r.json()["job_id"]
    for _ in range(30):
        jr = client.get(f"/api/job/{jid}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    # sitemap
    rs = client.get(f"/api/site/{jid}/sitemap.xml")
    assert rs.status_code == 200, rs.text
    assert "<urlset" in rs.text
    assert f"/api/site/{jid}" in rs.text
    assert rs.headers["content-type"].startswith("application/xml")
    # robots
    rr = client.get(f"/api/site/{jid}/robots.txt")
    assert rr.status_code == 200
    assert "Sitemap:" in rr.text
    assert f"/api/site/{jid}/sitemap.xml" in rr.text

def test_vcard_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    appmod._RATE.clear()
    r = client.post("/api/generate", json={"name": "Анна Смирнова", "about": "Арт-директор студии Свет", "products": "", "advantages": "", "extras": "Москва", "theme_mode": "light", "accent": "rose", "email": "b@c.ru", "kind": "vcard"})
    jid = r.json()["job_id"]
    for _ in range(30):
        jr = client.get(f"/api/job/{jid}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    rv = client.get(f"/api/site/{jid}/vcard")
    assert rv.status_code == 200
    assert rv.headers["content-type"].startswith("text/vcard")
    txt = rv.text
    assert "BEGIN:VCARD" in txt
    assert "FN:Анна" in txt or "FN:Анна Смирнова" in txt
    assert "END:VCARD" in txt
    assert "attachment" in rv.headers.get("content-disposition", "")

def test_publish_static(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    appmod._RATE.clear()
    r = client.post("/api/generate", json={"name": "Static Pub", "about": "Тест для публикации на хостинг", "products": "Услуга", "advantages": "", "extras": "", "theme_mode": "light", "accent": "purple", "email": "c@d.ru", "kind": "taplink"})
    jid = r.json()["job_id"]
    for _ in range(30):
        jr = client.get(f"/api/job/{jid}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    appmod._RATE.clear()
    rp = client.post(f"/api/publish/static/{jid}")
    assert rp.status_code == 200, rp.text
    j = rp.json()
    assert j["ok"] is True
    assert f"/api/site/{jid}" in j["url"]

def test_publish_s3_without_config(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "is_configured", lambda: False)
    appmod._RATE.clear()
    r = client.post("/api/generate", json={"name": "S3 Test", "about": "Тест S3 публикации без бакета", "products": "", "advantages": "", "extras": "", "theme_mode": "light", "accent": "teal", "email": "d@e.ru", "kind": "landing"})
    jid = r.json()["job_id"]
    for _ in range(30):
        jr = client.get(f"/api/job/{jid}").json()
        if jr["status"] != "running":
            break
        time.sleep(0.2)
    assert jr["status"] == "done"
    appmod._RATE.clear()
    # ensure no S3 env
    monkeypatch.delenv("SITEGEN_S3_BUCKET", raising=False)
    # also patch storage.S3_BUCKET to empty
    import storage
    monkeypatch.setattr(storage, "S3_BUCKET", "")
    monkeypatch.setattr(storage, "_s3_client", None, raising=False)
    # force is_s3 to False
    monkeypatch.setattr(storage, "is_s3", lambda: False)
    rp = client.post(f"/api/publish/s3/{jid}")
    assert rp.status_code == 503
    assert "S3 не настроен" in rp.text

def test_config_s3_field(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    j = r.json()
    assert "s3" in j
    assert "s3_bucket" in j
    assert isinstance(j["s3"], bool)
