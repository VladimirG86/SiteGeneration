"""Eval-харнес: метрики и детектор клише (офлайн, без судьи и скриншотов)."""
import json

import chat
import demo_content
import eval as evalmod
import sections


def _built(niche_about="Кофейня в Казани, своя обжарка."):
    site = chat.normalize_site(demo_content.build_site(
        {"Название": "T", "О бизнесе": niche_about, "Услуги/товары": "Латте - 280",
         "Преимущества": "Вкусно", "Дополнительно": ""}, "light", "blue"))
    return site, sections.render_page(dict(site), site_id="ev")


def test_metrics_clean_demo():
    m = evalmod.metrics_for(*_built())
    assert m["order_ok"] and m["has_form"] and m["anchors_unique"]
    assert m["cliches"] == []
    assert m["sections"] == 9 and m["prices_with_digits"] >= 1 and m["faq_count"] >= 4


def test_cliche_detector_finds_planted():
    site, _ = _built()
    site["sections"][0]["subtitle"] = "Высокое качество и индивидуальный подход."
    m = evalmod.metrics_for(site, sections.render_page(dict(site), site_id="ev2"))
    assert "высокое качество" in m["cliches"] and "индивидуальный подход" in m["cliches"]


def test_run_writes_report(tmp_path):
    report = evalmod.run(niches=["auto", "food"], out=str(tmp_path))
    assert report["summary"]["cases"] == 2
    assert (tmp_path / "report.json").exists() and (tmp_path / "report.md").exists()
    data = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert data["summary"]["cliches_total"] == 0
