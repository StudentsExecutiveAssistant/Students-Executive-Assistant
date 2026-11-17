"""Тести парсингу та форматування дат, часових проміжків і розкладу."""
from __future__ import annotations

from datetime import date

from app.core import dates
from tests import helpers  # noqa: F401


def test_dates_and_schedule_in_memory() -> None:
    assert dates.format_dates("30.11.2026, 01.12.2026") == "30 листопада та 1 грудня 2026 року"
    assert dates.format_dates("30.11, 01.12.2026") == "30 листопада та 1 грудня 2026 року"
    assert dates.format_dates("23.10.2026, 26.10.2026") == "23 та 26 жовтня 2026 року"
    assert dates.format_dates("19.04, 26.04 та 03.05.2026") == "19, 26 квітня та 3 травня 2026 року"
    assert dates.format_dates("30.12.2026, 02.01.2027") == "30 грудня 2026 року та 2 січня 2027 року"

    assert dates.parse_dates("26 листопада 2026") == [(date(2026, 11, 26), date(2026, 11, 26))]
    assert dates.parse_dates("26 листопада", 2026) == [(date(2026, 11, 26), date(2026, 11, 26))]
    assert dates.parse_dates("26-28 листопада 2026") == [(date(2026, 11, 26), date(2026, 11, 28))]
    assert dates.format_dates("з 26.11 по 28.11.2026") == "26-28 листопада 2026 року"
    assert dates.format_dates("з 26 листопада до 2 грудня 2026") == "з 26 листопада до 2 грудня 2026 року"
    assert dates.format_dates("26.11.2026\n28.11.2026\n30.11.2026") == "26, 28 та 30 листопада 2026 року"

    sched = dates.parse_schedule("26.11.2026 16:00-20:30\n28.11.2026 14:00-18:00")
    assert sched == [
        (date(2026, 11, 26), date(2026, 11, 26), (16 * 60, 20 * 60 + 30)),
        (date(2026, 11, 28), date(2026, 11, 28), (14 * 60, 18 * 60)),
    ]
    assert dates.format_schedule(sched) == (
        "26 листопада з 16:00 год до 20:30 год та 28 листопада 2026 року з 14:00 год до 18:00 год"
    )
    assert dates.parse_schedule("26.11 - 28.11.2026") == [(date(2026, 11, 26), date(2026, 11, 28), None)]
    assert dates.parse_schedule("26.11 з 16:00 до 20:30", 2026) == [(date(2026, 11, 26), date(2026, 11, 26), (960, 1230))]
    assert dates.parse_schedule("26.11 з 16.00 до 20.30", 2026) == [(date(2026, 11, 26), date(2026, 11, 26), (960, 1230))]
    assert dates.parse_schedule("26.11 о 17:00", 2026) == [(date(2026, 11, 26), date(2026, 11, 26), (1020, None))]
    assert dates.parse_schedule("26.11 з 16 до 20", 2026) == [(date(2026, 11, 26), date(2026, 11, 26), (960, 1200))]
    assert dates.parse_schedule("26.11 16-20", 2026) == [(date(2026, 11, 26), date(2026, 11, 26), (960, 1200))]
    assert dates.parse_schedule("26.11.2026 15.00-18.00") == [(date(2026, 11, 26), date(2026, 11, 26), (900, 1080))]
    assert dates.parse_schedule("26.11.2026, 15.00-18.00") == [(date(2026, 11, 26), date(2026, 11, 26), (900, 1080))]

    for bad, kw in [
        ("26.11.2026, 28.11.2026 16:00-20:30", {}),
        ("26.11.2026 16:00-20:30", {"allow_time": False}),
        ("16:00-20:30", {}),
        ("11.15.2026", {}),
        ("12.15", {}),
        ("31.02.2026", {}),
    ]:
        try:
            dates.parse_schedule(bad, **kw)
            raise AssertionError(f"Expected ValueError for {bad!r}")
        except ValueError as err:
            msg = str(err)
            assert "month must be" not in msg and "day is out of range" not in msg, msg
