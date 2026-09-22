"""Промпты: короткий system, нишевый блок, схема на месте."""
import niches
import prompts

ANSWERS = {"Название": "T", "О бизнесе": "Автосервис в Казани."}


def test_system_is_brief_no_rule_duplication():
    msgs = prompts.build_site_messages(ANSWERS, "light", "Синий", "#2563eb", "auto")
    assert [m["role"] for m in msgs] == ["system", "user"]
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert len(system) < 1500  # бриф, а не половина правил
    assert "ТОЛЬКО валидным JSON" in system
    # детальные правила — только в user, без дубля в system
    assert "ЖЁСТКИЕ ПРАВИЛА" in user and "ЖЁСТКИЕ ПРАВИЛА" not in system
    assert '"sections"' in user and "Автосервис" in user


def test_niche_guide_injected_only_for_known_niche():
    auto = prompts.build_site_messages(ANSWERS, "light", "Синий", "#2563eb", "auto")[1]["content"]
    assert "НИША: автосервис" in auto and "диагностика 1 000" in auto
    generic = prompts.build_site_messages(ANSWERS, "light", "Синий", "#2563eb", "generic")[1]["content"]
    assert "НИША:" not in generic


def test_guides_cover_all_niches():
    for niche in niches.NICHE_KEYWORDS:
        g = prompts.NICHE_GUIDE.get(niche, "")
        assert len(g) > 200, niche
        assert "FAQ" in g and "Табу" in g, niche


def test_chips_messages_shape():
    msgs = prompts.build_chips_messages({"Компания": "T", "Описание": "Кафе"})
    assert msgs[0]["role"] == "system" and "products" in msgs[0]["content"]
    assert "Кафе" in msgs[1]["content"]
