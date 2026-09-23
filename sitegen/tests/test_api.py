"""API end-to-end на TestClient. Сеть не используется: LLM/картинки либо
выключены (демо-путь), либо замоканы. Сайты пишутся во временную папку."""
import json
import time

import pytest
from fastapi.testclient import TestClient

import app as appmod
import chat as chat_ops
import demo_content
import generator
import images
import llm
import sections


def _poll_done(client, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/job/{job_id}")
        assert r.status_code == 200
        if r.json()["status"] == "done":
            return r.json()
        assert r.json()["status"] == "running"
        time.sleep(0.5)
    raise TimeoutError("job не завершился")


def test_config_shape(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["llm"] is False and len(body["accents"]) == 6


def test_analyze_fallback_chips(client):
    r = client.post("/api/analyze", json={"name": "ШИНОМОНТАЖ24", "about": "Шиномонтаж в Казани"})
    assert r.status_code == 200
    body = r.json()
    assert body["niche"] == "auto"
    assert len(body["chips"]["products"]) == 9


def test_generate_poll_site_files(client, tmp_path):
    r = client.post("/api/generate", json={
        "name": "Brewhaus", "about": "Кофейня в Екатеринбурге, своя обжарка с 2019 года.",
        "products": "Латте - 280", "advantages": "Готовим при вас",
        "extras": "", "theme_mode": "light", "accent": "orange",
        "email": "t@t.ru"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    job = _poll_done(client, job_id)
    assert job["site_url"] == f"/api/site/{job_id}"
    html = client.get(f"/api/site/{job_id}")
    assert html.status_code == 200 and len(html.text) > 15000
    assert (tmp_path / f"{job_id}.json").exists()
    assert (tmp_path / f"{job_id}.html").exists()
    assert (tmp_path / f"{job_id}.history.json").exists()


def test_lead_and_leads(client):
    assert client.post("/api/lead/s1", json={"name": "А", "type": "form"}).json() == {"ok": True}
    assert client.post("/api/lead/s1", json={"name": "Б", "type": "cart",
                                             "items": [{"name": "x", "qty": 1}]}).json() == {"ok": True}
    leads = client.get("/api/leads/s1").json()
    assert [l["type"] for l in leads] == ["form", "cart"]


def test_leads_admin_token(client, monkeypatch):
    client.post("/api/lead/s2", json={"name": "А"})
    monkeypatch.setattr(appmod, "ADMIN_TOKEN", "secret")
    assert client.get("/api/leads/s2").status_code == 401
    assert client.get("/api/leads/s2?token=secret").status_code == 200
    assert client.get("/api/leads/s2", headers={"x-admin-token": "secret"}).status_code == 200


def test_undo_first_version_error(client, tmp_path):
    site = chat_ops.normalize_site(demo_content.build_site(
        {"Название": "T", "О бизнесе": "Кафе в Казани.", "Услуги/товары": "Кофе - 100",
         "Преимущества": "Вкусно", "Дополнительно": ""}, "light", "blue"))
    site["theme"] = {"mode": "light", "accent": "blue"}
    generator._save_all("v1", site, sections.render_page(dict(site), site_id="v1"), True)
    assert client.post("/api/undo/v1").status_code == 400


def test_chat_mocked_then_undo(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "API_KEY", "test-key")  # редактор «включён»
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps({
        "reply": "Тему сменил.",
        "ops": [{"op": "set_theme", "mode": "dark", "accent": "rose"}]}))
    site = chat_ops.normalize_site(demo_content.build_site(
        {"Название": "T", "О бизнесе": "Кафе в Казани.", "Услуги/товары": "Кофе - 100",
         "Преимущества": "Вкусно", "Дополнительно": ""}, "light", "blue"))
    site["theme"] = {"mode": "light", "accent": "blue"}
    generator._save_all("ed1", site, sections.render_page(dict(site), site_id="ed1"), True)

    r = client.post("/api/chat/ed1", json={"message": "сделай тёмную тему"})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == 1 and r.json()["version"] == 2
    assert client.get("/api/chat/progress/ed1").json() == {}
    # история чата — на диске (переживёт рестарт)
    assert (tmp_path / "ed1.chat.json").exists()

    u = client.post("/api/undo/ed1")
    assert u.json()["version"] == 1
    back = json.loads((tmp_path / "ed1.json").read_text(encoding="utf-8"))
    assert back["theme"] == {"mode": "light", "accent": "blue"}


def test_ratelimit_429(client, monkeypatch):
    monkeypatch.setattr(appmod, "_RATE", {})
    monkeypatch.setitem(appmod.RATE_LIMITS, "analyze", (2, 3600))
    body = {"name": "T", "about": "Кафе в Казани, завтраки."}
    assert client.post("/api/analyze", json=body).status_code == 200
    assert client.post("/api/analyze", json=body).status_code == 200
    assert client.post("/api/analyze", json=body).status_code == 429


def _seed_site(tmp_path, site_id="ed1"):
    site = chat_ops.normalize_site(demo_content.build_site(
        {"Название": "T", "О бизнесе": "Кафе в Казани.", "Услуги/товары": "Кофе - 100",
         "Преимущества": "Вкусно", "Дополнительно": ""}, "light", "blue"))
    site["theme"] = {"mode": "light", "accent": "blue"}
    generator._save_all(site_id, site, sections.render_page(dict(site), site_id=site_id), True)


def _sse_events(text):
    """Парсит text/event-stream в список (event, data)."""
    events = []
    for chunk in text.split("\n\n"):
        ev, data = None, None
        for line in chunk.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if ev:
            events.append((ev, data))
    return events


def test_chat_stream_mocked(client, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "API_KEY", "test-key")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps({
        "reply": "Готово.", "ops": [{"op": "set_theme", "mode": "dark"}]}))
    _seed_site(tmp_path, "sse1")
    r = client.get("/api/chat/stream/sse1", params={"message": "сделай тёмную тему"})
    assert r.status_code == 200, r.text
    assert "text/event-stream" in r.headers["content-type"]
    events = _sse_events(r.text)
    assert events[0][0] == "start"
    assert events[-1][0] == "done" and events[-1][1]["applied"] == 1


def test_chat_stream_validation(client, tmp_path):
    _seed_site(tmp_path, "sse2")
    assert client.get("/api/chat/stream/sse2", params={"message": "x"}).status_code == 400
    assert client.get("/api/chat/stream/nope", params={"message": "сделай тёмную"}).status_code == 404
    assert client.get("/api/chat/stream/..%2F..", params={"message": "сделай тёмную"}).status_code in (400, 404)


def test_leads_persisted_to_disk(client, tmp_path):
    client.post("/api/lead/disk1", json={"name": "А", "type": "form"})
    p = tmp_path / "disk1.leads.json"
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8"))[0]["name"] == "А"
    assert client.get("/api/leads/disk1").json()[0]["name"] == "А"


def test_job_id_guard(client):
    assert client.get("/api/job/..%2Fapp").status_code == 404
    assert client.get("/api/site/..%2Fapp").status_code == 404
    assert client.post("/api/undo/..%2Fapp").status_code == 404


def test_auth_smtp_disabled(client):
    assert client.post("/api/auth/code", json={"email": "a@b.ru"}).status_code == 503
    assert client.post("/api/auth/verify", json={"email": "a@b.ru", "code": "123456"}).status_code == 503
    assert client.get("/api/config").json()["auth"] is False


def test_auth_flow_mocked_smtp(client, monkeypatch):
    monkeypatch.setattr(appmod, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(appmod, "SMTP_USER", "u")
    monkeypatch.setattr(appmod, "SMTP_PASS", "p")
    monkeypatch.setattr(appmod, "SMTP_FROM", "n@t.co")
    sent = []
    monkeypatch.setattr(appmod, "_send_code_email", lambda to, code: sent.append((to, code)))
    monkeypatch.setattr(appmod, "_AUTH_CODES", {})

    assert client.get("/api/config").json()["auth"] is True
    r = client.post("/api/auth/code", json={"email": "User@Mail.ru"})
    assert r.status_code == 200, r.text
    assert sent and sent[0][0] == "user@mail.ru"
    code = appmod._AUTH_CODES["user@mail.ru"]["code"]
    # повторная отправка в кулдаун — 429
    assert client.post("/api/auth/code", json={"email": "user@mail.ru"}).status_code == 429
    # неверный код — 400, верный — ok (одноразовый)
    assert client.post("/api/auth/verify",
                       json={"email": "user@mail.ru", "code": "000000"}).status_code == 400
    assert client.post("/api/auth/verify",
                       json={"email": "user@mail.ru", "code": code}).json() == {"ok": True}
    assert client.post("/api/auth/verify",
                       json={"email": "user@mail.ru", "code": code}).status_code == 400
    # плохие email
    assert client.post("/api/auth/code", json={"email": "непочта"}).status_code == 400

def test_billing_checkout_paused(client):
    # без ключа Lava — должен вернуть paused url, не 503
    r = client.post("/api/billing/checkout", json={"tariff": "pro"})
    assert r.status_code == 200
    j = r.json()
    assert j.get("paused") is True
    assert "#prices" in j.get("url","")
    # yearly тоже ведёт на #prices с yearly=1
    ry = client.post("/api/billing/checkout", json={"tariff": "pro", "yearly": True})
    assert ry.json().get("url") == "/#prices?tariff=pro&yearly=1"
    # config должен отдавать billing_paused
    rc = client.get("/api/config").json()
    assert "billing_paused" in rc
    assert rc["billing_paused"] is True

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["service"] == "nelvi"
    assert "billing_paused" in j

