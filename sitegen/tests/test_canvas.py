import os

import json, io, zipfile
def test_canvas_crud_and_publish(client, tmp_path, monkeypatch):
    import app as appmod
    import generator
    # ensure CANVAS_DIR isolated
    monkeypatch.setattr(appmod, "CANVAS_DIR", str(tmp_path / "canvas"))
    os.makedirs(tmp_path / "canvas", exist_ok=True)
    monkeypatch.setattr(generator, "SITES_DIR", str(tmp_path / "sites"))
    os.makedirs(tmp_path / "sites", exist_ok=True)
    appmod._RATE.clear()

    # create via POST /api/canvases
    r=client.post("/api/canvases")
    assert r.status_code==200
    jid=r.json()["id"]
    assert jid

    # get empty
    r=client.get(f"/api/canvas/{jid}")
    assert r.status_code==200
    assert "blocks" in r.json()

    # save with validation - bad type should 400
    bad=[{"id":"h1","type":"bad","x":0,"y":0,"w":100,"h":100,"z":1,"props":{}}]
    r=client.post(f"/api/canvas/{jid}", json={"blocks": bad})
    assert r.status_code==400

    # save good with bg/h
    good=[{"id":"h1","type":"heading","x":48,"y":48,"w":520,"h":84,"z":1,"props":{"text":"Hello","size":36,"color":"#2B2B36"}}]
    r=client.post(f"/api/canvas/{jid}", json={"blocks": good, "bg":"#FFEEDD","h":900})
    assert r.status_code==200

    r=client.get(f"/api/canvas/{jid}")
    assert r.json()["bg"]=="#FFEEDD"
    assert r.json()["h"]==900
    assert len(r.json()["blocks"])==1

    # duplicate
    r=client.post(f"/api/canvas/{jid}/duplicate")
    assert r.status_code==200
    nid=r.json()["id"]
    assert nid!=jid
    r=client.get(f"/api/canvas/{nid}")
    assert r.json()["bg"]=="#FFEEDD"

    # publish
    r=client.post(f"/api/canvas/{jid}/publish")
    assert r.status_code==200

    # zip export
    r=client.get(f"/api/canvas/{jid}/zip")
    assert r.status_code==200
    assert r.headers["content-type"]=="application/zip"
    # check zip contains index.html and sitemap
    data=io.BytesIO(r.content)
    z=zipfile.ZipFile(data)
    assert "index.html" in z.namelist()
    assert "sitemap.xml" in z.namelist()

    # zip content checks
    r=client.get(f"/api/canvas/{jid}/zip")
    assert r.status_code==200
    assert r.headers["content-type"]=="application/zip"
    z=zipfile.ZipFile(io.BytesIO(r.content))
    assert "index.html" in z.namelist()
    assert "site.json" in z.namelist()
    html=z.read("index.html").decode()
    assert "Hello" in html
    assert "#FFEEDD" in html or "FFEEDD" in html  # bg may be in html

    # list
    r=client.get("/api/canvases")
    assert r.status_code==200
    assert any(c["id"]==jid for c in r.json()["canvases"])

    # delete
    r=client.delete(f"/api/canvas/{nid}")
    assert r.status_code==200
    r=client.get(f"/api/canvas/{nid}")
    assert r.json()["blocks"]==[]

    # publish S3 without config should 503
    r=client.post(f"/api/canvas/{jid}/publish/s3")
    assert r.status_code==503

    # canvas via generate kind=canvas
    r=client.post("/api/generate", json={"name":"CanvasTest","about":"About canvas test 12345","products":"","advantages":"","extras":"","theme_mode":"light","accent":"purple","kind":"canvas","email":"a@b.com"})
    assert r.status_code==200
    assert r.json()["kind"]=="canvas"
    cid=r.json()["job_id"]
    r=client.get(f"/api/canvas/{cid}")
    assert r.status_code==200
    assert len(r.json()["blocks"])>=1
    r=client.get(f"/api/site/{cid}/json")
    assert r.json()["kind"]=="canvas"

def test_canvas_validation_limits(client, tmp_path, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, "CANVAS_DIR", str(tmp_path / "canvas2"))
    os.makedirs(tmp_path / "canvas2", exist_ok=True)
    appmod._RATE.clear()
    r=client.post("/api/canvases")
    jid=r.json()["id"]
    # too many blocks
    many=[{"id":f"h{i}","type":"text","x":0,"y":0,"w":10,"h":10,"z":1,"props":{"text":"hi"}} for i in range(90)]
    r=client.post(f"/api/canvas/{jid}", json={"blocks": many})
    assert r.status_code==400
    # bad id
    r=client.post("/api/canvas/bad!id", json={"blocks": []})
    assert r.status_code==400
    # bad h
    r=client.post(f"/api/canvas/{jid}", json={"blocks": [], "h": 9999})
    assert r.status_code==422  # pydantic validation

def test_canvas_history_undo(client, tmp_path, monkeypatch):
    import app as appmod, generator, os, json
    monkeypatch.setattr(appmod, "CANVAS_DIR", str(tmp_path / "canvas_hist"))
    os.makedirs(tmp_path / "canvas_hist", exist_ok=True)
    monkeypatch.setattr(generator, "SITES_DIR", str(tmp_path / "sites_hist"))
    os.makedirs(tmp_path / "sites_hist", exist_ok=True)
    appmod._RATE.clear()
    r=client.post("/api/canvases")
    jid=r.json()["id"]
    good1=[{"id":"h1","type":"heading","x":0,"y":0,"w":100,"h":50,"z":1,"props":{"text":"v1","size":20,"color":"#000"}}]
    good2=[{"id":"h1","type":"heading","x":0,"y":0,"w":100,"h":50,"z":1,"props":{"text":"v2","size":20,"color":"#000"}}]
    r=client.post(f"/api/canvas/{jid}", json={"blocks": good1})
    assert r.status_code==200
    r=client.post(f"/api/canvas/{jid}", json={"blocks": good2})
    assert r.status_code==200
    r=client.get(f"/api/canvas/{jid}/history")
    assert r.status_code==200
    hist=r.json()["history"]
    assert len(hist)>=2  # at least one history + current
    assert r.json()["count"]>=1
    # undo should restore v1
    r=client.post(f"/api/canvas/{jid}/undo")
    assert r.status_code==200
    r=client.get(f"/api/canvas/{jid}")
    assert r.json()["blocks"][0]["props"]["text"]=="v1"
    # second undo restores default (3 blocks), third should fail
    r=client.post(f"/api/canvas/{jid}/undo")
    assert r.status_code==200
    r=client.post(f"/api/canvas/{jid}/undo")
    assert r.status_code==400

def test_canvas_brand_persist(client, tmp_path, monkeypatch):
    import app as appmod, generator
    monkeypatch.setattr(appmod, "CANVAS_DIR", str(tmp_path / "canvas_brand"))
    import os
    os.makedirs(tmp_path / "canvas_brand", exist_ok=True)
    monkeypatch.setattr(generator, "SITES_DIR", str(tmp_path / "sites_brand"))
    os.makedirs(tmp_path / "sites_brand", exist_ok=True)
    appmod._RATE.clear()
    r=client.post("/api/canvases")
    jid=r.json()["id"]
    r=client.post(f"/api/canvas/{jid}", json={"blocks":[{"id":"h1","type":"heading","x":0,"y":0,"w":100,"h":50,"z":1,"props":{"text":"hi","size":20,"color":"#000"}}], "brand":"TestBrand","bg":"#ABCDEF","h":850})
    assert r.status_code==200
    r=client.get(f"/api/canvas/{jid}")
    assert r.json()["brand"]=="TestBrand"
    r=client.get("/api/canvases")
    assert any(c["id"]==jid and c.get("brand")=="TestBrand" for c in r.json()["canvases"])
    r=client.post(f"/api/canvas/{jid}/publish")
    assert r.json()["ok"]
    r=client.get(f"/api/site/{jid}/json")
    assert r.json()["brand"]=="TestBrand"
    import zipfile, io
    r=client.get(f"/api/canvas/{jid}/zip")
    z=zipfile.ZipFile(io.BytesIO(r.content))
    html=z.read("index.html").decode()
    assert "TestBrand" in html
    assert "#ABCDEF" in html or "ABCDEF" in html

def test_canvas_theme(client, tmp_path, monkeypatch):
    import app as appmod, generator
    monkeypatch.setattr(appmod, "CANVAS_DIR", str(tmp_path / "canvas_theme"))
    import os
    os.makedirs(tmp_path / "canvas_theme", exist_ok=True)
    monkeypatch.setattr(generator, "SITES_DIR", str(tmp_path / "sites_theme"))
    os.makedirs(tmp_path / "sites_theme", exist_ok=True)
    appmod._RATE.clear()
    r=client.post("/api/canvases")
    jid=r.json()["id"]
    r=client.post(f"/api/canvas/{jid}", json={"blocks":[{"id":"h1","type":"heading","x":0,"y":0,"w":100,"h":50,"z":1,"props":{"text":"hi","size":20,"color":"#000"}}], "theme":{"mode":"dark","accent":"emerald"}})
    assert r.status_code==200
    r=client.get(f"/api/canvas/{jid}")
    assert r.json()["theme"]["mode"]=="dark"
    r=client.post(f"/api/canvas/{jid}/publish")
    assert r.status_code==200
    r=client.get(f"/api/site/{jid}/json")
    assert r.json()["theme"]["mode"]=="dark"
    assert r.json()["theme"]["accent"]=="emerald"
