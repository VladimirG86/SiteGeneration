"""ИИ-редактор: sanitize, id-адресация, apply_ops, normalize."""
import copy

import pytest

import chat
import demo_content


def _site():
    answers = {
        "Название": "Тест", "О бизнесе": "Кофейня в Казани, своя обжарка.",
        "Услуги/товары": "Латте - 280", "Преимущества": "Своя обжарка",
        "Дополнительно": "",
    }
    return chat.normalize_site(demo_content.build_site(answers, "light", "blue"))


# ------------------------------------------------------------- sanitize ----

def test_sanitize_keeps_good_id_drops_bad():
    good = chat.sanitize_section({"type": "faq", "id": "faq-2", "title": "t",
                                  "items": [{"q": "q?", "a": "a"}]})
    assert good["id"] == "faq-2"
    bad = chat.sanitize_section({"type": "faq", "id": "!!!", "title": "t",
                                 "items": [{"q": "q?", "a": "a"}]})
    assert "id" not in bad


def test_sanitize_process_accepts_steps_and_items():
    by_steps = chat.sanitize_section({"type": "process", "title": "t",
                                      "steps": [{"title": "Шаг", "desc": "d"}]})
    by_items = chat.sanitize_section({"type": "process", "title": "t",
                                      "items": [{"title": "Шаг", "desc": "d"}]})
    assert by_steps["steps"] == [{"title": "Шаг", "desc": "d"}]
    assert by_items["steps"] == [{"title": "Шаг", "desc": "d"}]


def test_sanitize_rejects_empty_and_unknown():
    assert chat.sanitize_section({"type": "prices", "items": []}) is None
    assert chat.sanitize_section({"type": "process", "steps": []}) is None
    assert chat.sanitize_section({"type": "nope"}) is None
    assert chat.sanitize_section("мусор") is None


# ---------------------------------------------------------- ensure_ids ----

def test_ensure_ids_stable_and_unique():
    site = _site()
    ids1 = [s["id"] for s in site["sections"]]
    assert len(ids1) == len(set(ids1)) and ids1[0] == "hero"
    chat.ensure_ids(site)  # повторный вызов ничего не меняет
    assert [s["id"] for s in site["sections"]] == ids1


def test_ensure_ids_keeps_existing_when_inserting_before():
    site = _site()
    old_faq_id = next(s["id"] for s in site["sections"] if s["type"] == "faq")
    site["sections"].insert(0, {"type": "faq", "title": "Новый первый",
                                "items": [{"q": "q?", "a": "a"}]})
    chat.ensure_ids(site)
    # новый блок получил свободный id, старый сохранил свой
    assert site["sections"][0]["id"] != old_faq_id
    assert next(s["id"] for s in site["sections"]
                if s.get("title") != "Новый первый" and s["type"] == "faq") == old_faq_id


def test_ensure_ids_migrates_legacy():
    site = _site()
    for s in site["sections"]:
        s.pop("id", None)
    chat.ensure_ids(site)
    assert all(s.get("id") for s in site["sections"])


# ---------------------------------------------------------- apply_ops -----

def test_upsert_replaces_by_type_by_default():
    site = _site()
    n = len(site["sections"])
    applied, _ = chat.apply_ops(site, [{"op": "upsert_section", "section": {
        "type": "faq", "title": "Новый FAQ",
        "items": [{"q": "q?", "a": "a"}]}}])
    assert applied == 1 and len(site["sections"]) == n
    assert next(s for s in site["sections"] if s["type"] == "faq")["title"] == "Новый FAQ"


def test_add_creates_second_block_with_unique_id():
    site = _site()
    applied, notes = chat.apply_ops(site, [{"op": "add_section", "after": "prices", "section": {
        "type": "faq", "title": "FAQ по доставке",
        "items": [{"q": "q?", "a": "a"}]}}])
    assert applied == 1 and not notes
    faqs = [s for s in site["sections"] if s["type"] == "faq"]
    assert len(faqs) == 2 and faqs[0]["id"] != faqs[1]["id"]
    # встал сразу после prices
    types = [s["type"] for s in site["sections"]]
    assert types[types.index("prices") + 1] == "faq"


def test_upsert_by_id_hits_exact_block():
    site = _site()
    chat.apply_ops(site, [{"op": "add_section", "section": {
        "type": "faq", "title": "Второй",
        "items": [{"q": "q?", "a": "a"}]}}])
    second_id = [s for s in site["sections"] if s["type"] == "faq"][1]["id"]
    chat.apply_ops(site, [{"op": "upsert_section", "section": {
        "type": "faq", "id": second_id, "title": "Обновлён",
        "items": [{"q": "q?", "a": "a"}]}}])
    faqs = [s for s in site["sections"] if s["type"] == "faq"]
    assert [f["title"] for f in faqs][1] == "Обновлён"


def test_singletons_cannot_duplicate():
    site = _site()
    applied, notes = chat.apply_ops(site, [{"op": "add_section", "section": {
        "type": "hero", "title": "Ещё один hero"}}])
    assert applied == 1 and notes  # заменил + предупредил
    assert sum(1 for s in site["sections"] if s["type"] == "hero") == 1


def test_same_type_limit():
    site = _site()
    mk = {"type": "faq", "title": "t", "items": [{"q": "q?", "a": "a"}]}
    chat.apply_ops(site, [{"op": "add_section", "section": copy.deepcopy(mk)}])
    chat.apply_ops(site, [{"op": "add_section", "section": copy.deepcopy(mk)}])
    applied, notes = chat.apply_ops(site, [{"op": "add_section", "section": copy.deepcopy(mk)}])
    assert applied == 0 and notes  # 4-й FAQ отклонён
    assert sum(1 for s in site["sections"] if s["type"] == "faq") == 3


def test_delete_and_move_by_id():
    site = _site()
    chat.apply_ops(site, [{"op": "add_section", "section": {
        "type": "faq", "title": "Второй", "items": [{"q": "q?", "a": "a"}]}}])
    second_id = [s for s in site["sections"] if s["type"] == "faq"][1]["id"]
    applied, _ = chat.apply_ops(site, [{"op": "move_section", "id": second_id, "after": "top"}])
    assert applied == 1 and site["sections"][0]["id"] == second_id
    applied, _ = chat.apply_ops(site, [{"op": "delete_section", "id": second_id}])
    assert applied == 1
    assert sum(1 for s in site["sections"] if s["type"] == "faq") == 1


def test_delete_missing_and_last_guarded():
    site = _site()
    _, notes = chat.apply_ops(site, [{"op": "delete_section", "type": "nope"}])
    assert notes
    tiny = {"sections": [{"type": "hero", "id": "hero", "title": "t"}]}
    applied, notes = chat.apply_ops(tiny, [{"op": "delete_section", "type": "hero"}])
    assert applied == 0 and notes


def test_theme_info_nav_feature():
    site = _site()
    applied, _ = chat.apply_ops(site, [
        {"op": "set_theme", "mode": "dark", "accent": "orange"},
        {"op": "set_info", "phone": "+7 (900) 1-2-3"},
        {"op": "set_nav", "nav": [{"label": "Каталог", "href": "#catalog"}]},
        {"op": "set_feature", "name": "cart", "enabled": True},
    ])
    assert applied == 4
    assert site["theme"] == {"mode": "dark", "accent": "orange"}
    assert site["features"] == {"cart": True}


# ---------------------------------------------------------- normalize -----

def test_normalize_assigns_ids_and_raises_on_garbage():
    site = _site()
    assert all(s.get("id") for s in site["sections"])
    with pytest.raises(ValueError):
        chat.normalize_site({"brand": "x"})
    with pytest.raises(ValueError):
        chat.normalize_site({"sections": [{"type": "prices", "items": []}]})


def test_editor_messages_contain_ids():
    site = _site()
    msgs = chat.build_editor_messages(site, [], "смени тему")
    assert '"id":"hero"' in msgs[-1]["content"] or '"id": "hero"' in msgs[-1]["content"]

def test_set_theme_russian_aliases():
    import chat as c
    for acc, expect in [("синий","blue"),("Синий","blue"),("мятный","emerald"),("оранжевый","orange"),("персик","rose"),("графит","teal"),("фиолетовый","purple")]:
        site={"theme":{"mode":"light","accent":"purple"},"sections":[{"type":"hero"},{"type":"contacts"}]}
        applied,_=c.apply_ops(site,[{"op":"set_theme","accent":acc}])
        assert site["theme"]["accent"]==expect, f"{acc} -> {site['theme']['accent']}"
        assert applied==1
    for mode, expect in [("темная","dark"),("тёмная тема","dark"),("светлая","light"),("ночной","dark")]:
        site={"theme":{"mode":"light","accent":"purple"},"sections":[{"type":"hero"},{"type":"contacts"}]}
        c.apply_ops(site,[{"op":"set_theme","mode":mode}])
        assert site["theme"]["mode"]==expect

