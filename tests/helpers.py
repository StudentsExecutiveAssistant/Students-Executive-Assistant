"""Спільні тестові дані, асерти розмітки Word-документів та клієнтська сесія для тестування бота в пам'яті."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from app.core import dates, templates
from app.docx import validator

OUT_DIR = Path(__file__).resolve().parent / "out"
REF_TODAY = date(2026, 10, 20)
BEST_REASON = "організацією та участю в BEST Engineering Competition від організації BEST Lviv"
BEST_DATE_INPUT = "23-27.10.2026"
BEST_DATE = dates.format_dates(BEST_DATE_INPUT)

STUDS_IKTA_21 = [
    "Бойко Божена, КБ-305",
    "Гандзюк Владислав, КБ-111",
    "Олійник Вікторію, КІ-207",
    "Мартинюк Дмитро, КБ-406",
    "Кицмен Євгеній, КІ-201",
    "Пидорич Нікіта, КБ-109",
    "Козловська Катерина, ІР-21",
    "Вотусь Ганна, ІР-22",
    "Даніїл Душинський, КІ-406",
    "Ігор Лінчевський, КІ-406",
    "Матусевич Ярослав, ІР-14",
    "Біляк Діана, ІР-14",
    "Козак Владислав, ІР-14",
    "Шубіна Надія, КІ-108",
    "Марцінковський Степан, ІР-31",
    "Скарбарчук Денис, КІ-107",
    "Ільєв Ілля, КІ-409",
    "Кіріл Омельченко, ІР-12",
    "Вишніцький Андрій, ІВ-12",
    "Віталій Чемерис, ІВ-12",
    "Сергієнко Владислав, КІ-103",
]

STUDS_IKNI_37 = [
    "Лисяк Яніна, СА-32",
    "Олефір Ксенія, ПЗ-44",
    "Лукащик Діана, ПЗ-27",
    "Журба Софія, ПЗ-22",
    "Клименко Нікіта, ITIC-11",
    "Д’яченко Назар, ОІ-31",
    "Морозова Анна, ПЗ-32",
    "Бідун Ольга, СА-13",
    "Вац Каміла, ПП-23",
    "Ковель Олексій, ПП-23",
    "Мінчак Ярина, ФЛ-16",
    "Мацевич Назар, ШІ-24",
    "Тимейчук Максим, ШІ-24",
    "Іванюк Арсен, ОІ-14",
    "Доценко Софія, ВР-11",
    "Щевчук Дем’ян, ВР-13",
    "Ярко Захар, ПП-45",
    "Рубан Лев, ПЗ-13",
    "Думанська Наталія, ПЗ-33",
    "Котюк Софія, ПЗ-32",
    "Федорінін Олександр, ОІ-45",
    "Сеник Денис, ПЗ-13",
    "Опришко Юрій, ПЗ-13",
    "Соколов Назар, ПЗ-13",
    "Нікіфореску Марк-Тіберій, ПЗ-13",
    "Калюк Ілля, ПЗ-13",
    "Процик Юрій, ПЗ-13",
    "Наврощук Арсен, ПЗ-37",
    "Карабінович Василь, ПП-36",
    "Дем’яненко Андрій, ПЗ-34",
    "Мєдєнцов Валентин, ПЗ-31",
    "Лотоцький Віталій, ПЗ-36",
    "Намофілов Владислав, ПЗ-35",
    "Волик Олексій, ПП-15",
    "Пивнюк Микола, ПП-15",
    "Кирил Чуєнко, ПП-15",
    "Девдюк Стас, ОІ-11",
]

STUDS_IBIB_4 = [
    "Андрій Федик, БД-206",
    "Тетяна Постол, БД-107",
    "Олексій Концур, БД-102",
    "Владислав Теслюк, БД-118",
]

STUDS_IARD_4 = [
    "Олександра Філоненко, АР-106",
    "Марія Яводчак, АР-117",
    "Уляна Малину, АР-301",
    "Марія Мельничук, АР-204",
]


def make_spec(tid: str, a: dict) -> dict:
    return templates.build_spec(tid, a)


def absence_answers(inst: str, studs: list[str]) -> dict:
    return {
        "inst": inst,
        "date": BEST_DATE,
        "_dates": [[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(BEST_DATE_INPUT)],
        "reason": BEST_REASON,
        "students": studs,
    }


def assert_clean_check(tid: str, a: dict, spec: dict, data: bytes) -> None:
    issues = validator.check(tid, a, spec, today=REF_TODAY)
    assert not any(lv in ("err", "warn") for lv, _ in issues), issues
    rep = validator.check_docx(data, today=REF_TODAY)
    assert "Знайшов клопотань: <b>1</b>" in rep[0], rep
    assert not any("❌" in line or "⚠️" in line for line in rep), rep


def assert_two_col_table_layout(tbl, left_cm: float = 8.5, right_cm: float = 8.5) -> tuple:
    tbl_pr = tbl._tbl.tblPr
    assert tbl_pr.tblLayout is not None and tbl_pr.tblLayout.type == "fixed"
    borders = tbl_pr.find(qn("w:tblBorders"))
    assert borders is not None
    assert all(
        (side_el := borders.find(qn(f"w:{s}"))) is not None and side_el.get(qn("w:val")) == "none"
        for s in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    c0, c1 = tbl.rows[0].cells
    assert c0.width is not None and c1.width is not None
    assert abs(c0.width - Cm(left_cm)) < Cm(0.01) and abs(c1.width - Cm(right_cm)) < Cm(0.01)
    grid = [int(el.get(qn("w:w"))) for el in tbl._tbl.tblGrid.findall(qn("w:gridCol"))]
    assert len(grid) == 2
    assert abs(grid[0] - Cm(left_cm).twips) <= 2 and abs(grid[1] - Cm(right_cm).twips) <= 2
    assert c0._tc.tcPr is not None and c1._tc.tcPr is not None
    m0 = c0._tc.tcPr.find(qn("w:tcMar"))
    m1 = c1._tc.tcPr.find(qn("w:tcMar"))
    assert m0 is not None and m1 is not None
    for side, expected in (("left", "0"), ("right", "170")):
        el0 = m0.find(qn(f"w:{side}"))
        assert el0 is not None and el0.get(qn("w:w")) == expected
    for side, expected in (("left", "170"), ("right", "0")):
        el1 = m1.find(qn(f"w:{side}"))
        assert el1 is not None and el1.get(qn("w:w")) == expected
    return c0, c1


def assert_hanging(p, indent_cm: float, first_cm: float, tab_cm: float, *, keep: bool | None) -> None:
    pf = p.paragraph_format
    assert pf.line_spacing == 1.15
    assert abs(pf.left_indent - Cm(indent_cm)) < Cm(0.01)
    assert abs(pf.first_line_indent - Cm(first_cm)) < Cm(0.01)
    assert len(pf.tab_stops) == 1 and abs(pf.tab_stops[0].position - Cm(tab_cm)) < Cm(0.01)
    assert pf.keep_with_next is keep
    assert p.runs[0].font.name == "Times New Roman"
    assert p.runs[0].font.size == Pt(14)


def make_fake_bot_harness(start_mid: int = 100):
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.client.session.base import BaseSession
    from aiogram.enums import ParseMode
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.methods import (
        AnswerCallbackQuery,
        EditMessageReplyMarkup,
        EditMessageText,
        SendDocument,
        SendMessage,
    )
    from aiogram.types import CallbackQuery, Chat, Message, Update, User
    from app import bot as bot_mod

    class FakeSession(BaseSession):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list = []
            self.next_mid = start_mid

        async def make_request(self, bot, method, timeout=None):
            self.calls.append(method)
            if isinstance(method, SendMessage):
                self.next_mid += 1
                return Message(
                    message_id=self.next_mid,
                    date=datetime.now(timezone.utc),
                    chat=Chat(id=int(method.chat_id), type="private"),
                    text=method.text,
                    reply_markup=method.reply_markup,
                )
            if isinstance(method, EditMessageText):
                return Message(
                    message_id=int(method.message_id),
                    date=datetime.now(timezone.utc),
                    chat=Chat(id=int(method.chat_id), type="private"),
                    text=method.text,
                    reply_markup=method.reply_markup,
                )
            if isinstance(method, SendDocument):
                self.next_mid += 1
                return Message(
                    message_id=self.next_mid,
                    date=datetime.now(timezone.utc),
                    chat=Chat(id=int(method.chat_id), type="private"),
                    caption=method.caption,
                )
            return True

        async def close(self) -> None:
            return None

        @asynccontextmanager
        async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
            yield iter(())

    session = FakeSession()
    bot = Bot("42:TEST_TOKEN", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.callback_query.middleware(bot_mod.StaleGuard())
    dp.include_router(bot_mod.router)
    return session, bot, storage, dp, StorageKey, CallbackQuery, Chat, Message, Update, User, (
        SendMessage,
        EditMessageText,
        EditMessageReplyMarkup,
        AnswerCallbackQuery,
        SendDocument,
    )
