"""Оценка качества генераций: структурные метрики + опционально скриншоты и LLM-судья.

Использование (из папки sitegen):
  python eval.py                        # офлайн-метрики по всем нишам
  python eval.py --niches auto,food     # только выбранные ниши
  python eval.py --judge                 # + LLM-судья (нужны ключ и сеть)
  python eval.py --shots                 # + скриншоты (нужен playwright+chromium)

Отчёт: eval_reports/report.json + report.md (+ shots/*.png).
Демо-контент детерминирован — метрики стабильны от запуска к запуску и
ловят регрессии (потерянные секции, клише, битые якоря).
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chat
import demo_content
import sections

EVAL_CASES = [
    ("АвтоПрофи", "Автосервис в Казани, ремонт двигателей с 2015 года",
     "Диагностика - 1500\nРемонт двигателя - от 8000", "Гарантия 12 месяцев", "auto"),
    ("Улыбка+", "Стоматология в Москве, лечение и имплантация",
     "Чистка - 5000\nИмплант под ключ - 45000", "Лечение без боли", "dental"),
    ("Шарм", "Салон красоты в СПб, стрижки и окрашивание",
     "Стрижка - 1800\nОкрашивание - от 6000", "Мастера с портфолио", "beauty"),
    ("Brewhaus", "Кофейня в Екатеринбурге, своя обжарка",
     "Латте - 280\nКруассан - 190", "Готовим при вас", "food"),
    ("Атлант", "Фитнес-клуб в Новосибирске", "Абонемент - 3500\nПерсоналка - 2000",
     "Пробная тренировка бесплатно", "fitness"),
    ("ДомСтрой", "Строительство домов в Краснодаре", "Проект - бесплатно",
     "Договор с фиксированной ценой", "build"),
    ("Лингва", "Школа английского в Самаре", "Группа - 8000\nИндивидуально - 1800",
     "Пробное занятие бесплатно", "edu"),
    ("МедЛайн", "Медцентр в Уфе: диагностика и врачи", "МРТ - от 6000\nПриём - 2000",
     "Результаты в день обращения", "med"),
    ("ПравоВед", "Юридические услуги в Ростове-на-Дону", "Консультация - 3000",
     "Опыт 15 лет", "law"),
    ("Квадрат", "Агентство недвижимости в Сочи", "Подбор квартиры - 2%",
     "Проверка юридической чистоты", "realestate"),
    ("Пиксель", "Веб-студия в Перми", "Лендинг - от 60000", "Запуск за 14 дней", "it"),
]

CLICHES = ["высокое качество", "высочайшее качество", "индивидуальный подход",
           "команда профессионалов", "широкий ассортимент", "доступные цены",
           "низкие цены", "лучшие на рынке", "лучший в городе", "многолетний опыт"]


def metrics_for(site: dict, html: str) -> dict:
    types = [s.get("type") for s in site.get("sections", [])]
    hero = next((s for s in site.get("sections", []) if s.get("type") == "hero"), {})
    texts = json.dumps(site, ensure_ascii=False).lower()
    prices = [it["price"] for s in site.get("sections", []) for it in (s.get("items") or [])
              if isinstance(it, dict) and it.get("price")]
    ids = re.findall(r'id="([^"]+)"', html)
    return {
        "sections": len(types),
        "order_ok": bool(types) and types[0] == "hero" and types[-1] == "contacts",
        "h1_len": len(hero.get("title", "")),
        "cliches": [c for c in CLICHES if c in texts],
        "prices_total": len(prices),
        "prices_with_digits": sum(1 for p in prices if re.search(r"\d", p)),
        "faq_count": sum(len(s.get("items") or []) for s in site.get("sections", [])
                         if s.get("type") == "faq"),
        "has_form": "lead-form" in html,
        "html_kb": round(len(html) / 1024, 1),
        "anchors_unique": len(ids) == len(set(ids)),
    }


def judge_site(site: dict) -> dict:
    """LLM-судья: оценки 1–5 + вердикт. Бросает исключение без сети/ключа."""
    import llm
    import prompts
    raw = llm.chat(prompts.build_judge_messages(site),
                   temperature=0.2, max_tokens=800, timeout=120)
    data = llm.extract_json(raw)
    scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    return {"scores": {k: scores.get(k) for k in ("concreteness", "no_fluff", "structure")},
            "verdict": str(data.get("verdict", ""))[:400]}


def screenshot(html: str, path: str):
    """Рендер скриншота через playwright. Бросает исключение, если нет браузера."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_content(html)
        page.wait_for_timeout(600)
        page.screenshot(path=path)
        browser.close()


def run(niches=None, judge=False, shots=False, out="eval_reports") -> dict:
    os.makedirs(out, exist_ok=True)
    cases = [c for c in EVAL_CASES if not niches or c[4] in niches]
    results = []
    for name, about, prod, adv, niche in cases:
        site = chat.normalize_site(demo_content.build_site(
            {"Название": name, "О бизнесе": about, "Услуги/товары": prod,
             "Преимущества": adv, "Дополнительно": ""}, "light", "blue"))
        html = sections.render_page(dict(site), site_id=f"eval-{niche}")
        entry = {"niche": niche, "brand": name, "metrics": metrics_for(site, html)}
        if judge:
            try:
                entry["judge"] = judge_site(site)
            except Exception as e:  # noqa: BLE001 — судья опционален
                entry["judge"] = {"error": str(e)[:200]}
        if shots:
            try:
                shots_dir = os.path.join(out, "shots")
                os.makedirs(shots_dir, exist_ok=True)
                shot_path = os.path.join(shots_dir, f"{niche}.png")
                screenshot(html, shot_path)
                entry["shot"] = os.path.relpath(shot_path, out)
            except Exception as e:  # noqa: BLE001 — скриншоты опциональны
                entry["shot_error"] = str(e)[:200]
        results.append(entry)
    summary = {
        "cases": len(results),
        "order_ok": sum(1 for r in results if r["metrics"]["order_ok"]),
        "cliches_total": sum(len(r["metrics"]["cliches"]) for r in results),
        "anchors_ok": sum(1 for r in results if r["metrics"]["anchors_unique"]),
        "avg_html_kb": round(sum(r["metrics"]["html_kb"] for r in results) / max(len(results), 1), 1),
    }
    report = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "summary": summary, "results": results}
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "report.md"), "w", encoding="utf-8") as f:
        f.write(_markdown(report))
    return report


def _markdown(report: dict) -> str:
    s = report["summary"]
    lines = [f"# Eval-отчёт ({report['at']})", "",
             f"Кейсов: {s['cases']}, порядок hero→…→contacts: {s['order_ok']}, "
             f"клише всего: {s['cliches_total']}, уникальные якоря: {s['anchors_ok']}, "
             f"средний HTML: {s['avg_html_kb']} КБ", "",
             "| Ниша | Секций | H1 | Клише | Цены с цифрами | FAQ | HTML | Судья |",
             "|---|---|---|---|---|---|---|---|"]
    for r in report["results"]:
        m = r["metrics"]
        j = r.get("judge") or {}
        score = ""
        if isinstance(j.get("scores"), dict) and any(j["scores"].values()):
            score = ",".join(str(j["scores"].get(k, "?"))
                             for k in ("concreteness", "no_fluff", "structure"))
        elif j.get("error"):
            score = "ошибка"
        lines.append(f"| {r['niche']} | {m['sections']} | {m['h1_len']} | "
                     f"{len(m['cliches'])} | {m['prices_with_digits']}/{m['prices_total']} | "
                     f"{m['faq_count']} | {m['html_kb']} КБ | {score} |")
    for r in report["results"]:
        j = r.get("judge") or {}
        if j.get("verdict"):
            lines += ["", f"## {r['niche']}: {j['verdict']}"]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Оценка качества генераций СБОРКА")
    ap.add_argument("--niches", default="", help="ниши через запятую, пусто = все")
    ap.add_argument("--judge", action="store_true", help="LLM-судья (нужны ключ и сеть)")
    ap.add_argument("--shots", action="store_true", help="скриншоты (нужен playwright)")
    ap.add_argument("--out", default="eval_reports", help="папка отчёта")
    args = ap.parse_args()
    niches = [n.strip() for n in args.niches.split(",") if n.strip()] or None
    report = run(niches=niches, judge=args.judge, shots=args.shots, out=args.out)
    s = report["summary"]
    print(f"кейсов: {s['cases']} | порядок ок: {s['order_ok']} | клише: {s['cliches_total']} | "
          f"якоря ок: {s['anchors_ok']} | средний HTML: {s['avg_html_kb']} КБ")
    print(f"отчёт: {args.out}/report.md")


if __name__ == "__main__":
    main()
