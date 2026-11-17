"""Тести автовиправлення тексту, очищення префіксів та нормалізації списків студентів."""
from __future__ import annotations

from app.core import cleaners, templates
from tests.helpers import BEST_DATE, BEST_REASON, STUDS_IBIB_4


def test_normalize_students() -> None:
    raw = [
        "  1. Бойко Божена, кб-305; ",
        "2) Д’яченко Назар оі-31.",
        "- Д'яченко Назар ОІ-31,",
        "•   ",
        "– Ільєв Ілля, кі-409",
        "3.",
        "  ",
        "— Нікіфореску Марк-Тіберій пз-13;",
        "5. Клименко Нікіта, ITIC-11",
    ]
    got = cleaners.normalize_students(raw)
    assert got == [
        "Бойко Божена, КБ-305",
        "Д’яченко Назар ОІ-31",
        "Д’яченко Назар ОІ-31",
        "Ільєв Ілля, КІ-409",
        "Нікіфореску Марк-Тіберій ПЗ-13",
        "Клименко Нікіта, ITIC-11",
    ], got


def test_clean_purpose_and_names() -> None:
    assert cleaners.clean_purpose("для проведення кіновечора") == ("проведення кіновечора", ["прибрано зайве «для»"])
    assert cleaners.clean_purpose("Для: для організації") == ("організації", ["прибрано зайве «для»"])
    assert cleaners.clean_purpose("проведення заходу для") == ("проведення заходу", ["прибрано зайве «для»"])
    assert cleaners.clean_purpose("для проведення заходу для студентів") == (
        "проведення заходу для студентів",
        ["прибрано зайве «для»"],
    )
    assert cleaners.clean_purpose("для того, щоб провести ярмарок") == ("для того, щоб провести ярмарок", [])
    assert cleaners.clean_purpose("з метою проведення промоакції", mode="meta") == (
        "проведення промоакції",
        ["прибрано зайве «з метою»"],
    )
    assert cleaners.clean_purpose("з метою для того, щоб провести ярмарок", mode="meta") == (
        "для того, щоб провести ярмарок",
        ["прибрано зайве «з метою»"],
    )
    for bad in ("для", "Для:", "   "):
        try:
            cleaners.clean_purpose(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {bad!r}")
    try:
        cleaners.clean_purpose("з метою", mode="meta")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for bare 'з метою' in meta mode")

    names, warns = cleaners.parse_names("іванов іван, Петренко Петро, іванов іван")
    assert names == ["Іванов Іван", "Петренко Петро", "Іванов Іван"]
    assert any("Повтори: Іванов Іван" in w for w in warns)


def test_reason_and_preposition_parsing_in_memory() -> None:
    assert cleaners.sanitize("у зв’язку з з з організацією та та участю") == (
        "у зв’язку з організацією та участю",
        ["подвоєні прийменники"],
    )
    assert cleaners.sanitize("зустріч з З. І. Мельником") == ("зустріч з З. І. Мельником", [])
    assert cleaners.sanitize("зустріч з З") == ("зустріч з З", [])

    assert cleaners.clean_reason(f"з {BEST_REASON}") == (BEST_REASON, ["прибрано зайве «з»"])
    assert cleaners.clean_reason("з з організацією") == ("організацією", ["прибрано зайве «з»"])
    assert cleaners.clean_reason("із проведенням форуму") == ("проведенням форуму", ["прибрано зайве «з»"])
    assert cleaners.clean_reason("зі змаганнями") == ("змаганнями", ["прибрано зайве «з»"])
    assert cleaners.clean_reason("у зв’язку з організацією") == ("організацією", ["прибрано зайве «у зв’язку з»"])
    assert cleaners.clean_reason("у зв'язку з з організацією") == (
        "організацією",
        ["прибрано зайве «у зв’язку з»", "прибрано зайве «з»"],
    )
    assert cleaners.clean_reason("в звязку із проведенням") == ("проведенням", ["прибрано зайве «у зв’язку з»"])
    assert cleaners.clean_reason("у зв’язку з у зв’язку з організацією") == (
        "організацією",
        ["прибрано зайве «у зв’язку з»"],
    )
    assert cleaners.clean_reason("з-за хвороби") == ("з-за хвороби", [])
    assert cleaners.clean_reason("зборами студентів") == ("зборами студентів", [])
    assert cleaners.clean_reason("зібранням активу") == ("зібранням активу", [])
    for bad in ("з", "із", "зі", "у зв’язку з", "в звязку:", "   "):
        try:
            cleaners.clean_reason(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {bad!r}")

    assert cleaners.clean_reason("за за активну діяльність", mode="za") == (
        "активну діяльність",
        ["прибрано зайве «за»"],
    )
    assert cleaners.clean_reason("заохочення студентів", mode="za") == ("заохочення студентів", [])
    for bad_za in ("за", "За:", "   "):
        try:
            cleaners.clean_reason(bad_za, mode="za")
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {bad_za!r}")

    assert cleaners.clean_route("для для поїздки у Карпати") == ("у Карпати", ["прибрано зайве «для»"])
    assert cleaners.clean_route("поїздки у Карпати") == ("у Карпати", ["прибрано зайве «для»"])
    assert cleaners.clean_dept("від туристичного відділу") == ("туристичного відділу", ["прибрано зайве «від»"])
    assert cleaners.clean_project("в межах проєкту «Плацкарт»") == ("проєкту «Плацкарт»", ["прибрано зайве «в межах»"])
    assert cleaners.clean_order("згідно з наказом № 168-1-10") == ("168-1-10", ["прибрано зайве «№»"])
    assert cleaners.clean_dorm("гуртожиток № 5") == ("5", ["прибрано зайве «гуртожиток»", "прибрано зайве «№»"])

    p_abs, _ = templates.b_absence({"date": BEST_DATE, "reason": f"з {BEST_REASON}", "students": STUDS_IBIB_4})
    assert f"у зв’язку з {BEST_REASON}" in p_abs[0]["t"] and "з з" not in p_abs[0]["t"], p_abs
    p_abs2, _ = templates.b_absence(
        {"date": BEST_DATE, "reason": f"у зв’язку з з {BEST_REASON}", "students": STUDS_IBIB_4}
    )
    assert f"у зв’язку з {BEST_REASON}" in p_abs2[0]["t"] and "у зв’язку з у зв’язку" not in p_abs2[0]["t"], p_abs2
    p_veh, _ = templates.b_vehicles(
        {"building": "навчального корпусу №1", "date": BEST_DATE, "reason": "із підготовкою", "plates": "ВС1640ЕР"}
    )
    assert "у зв’язку з підготовкою" in p_veh[0]["t"], p_veh
    p_bus, _ = templates.b_bus(
        {"route": "для поїздки у Карпати", "date": BEST_DATE, "dept": "від туристичного відділу"}
    )
    assert "для поїздки у Карпати" in p_bus[0]["t"] and "від туристичного відділу" in p_bus[0]["t"], p_bus
    p_gst, _ = templates.b_guest(
        {"who": "чотирьох осіб", "date": BEST_DATE, "project": "в межах проєкту «Плацкарт»"}
    )
    assert "в межах проєкту «Плацкарт»" in p_gst[0]["t"] and "в межах в межах" not in p_gst[0]["t"], p_gst
    p_awd, _ = templates.b_award(
        {"form": "бюджетної", "reason": "за активну діяльність", "students": [["Оршак Максим", "ІПМТ", "РК-31"]]}
    )
    assert "преміювати за активну діяльність" in p_awd[0]["t"], p_awd
