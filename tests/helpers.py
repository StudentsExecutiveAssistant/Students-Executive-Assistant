"""Спільні тестові дані, асерти розмітки Word-документів та клієнтська сесія для тестування бота в пам'яті."""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from docx.shared import Cm, Pt

from app.core import dates, templates
from app.docx import validator

OUT_DIR = Path(__file__).resolve().parent / "out"
REF_TODAY = date(2026, 10, 20)
BEST_REASON = (
	"організацією та участю в BEST Engineering Competition від організації BEST Lviv"
)
BEST_DATE_INPUT = "23-27.10.2026"
BEST_DATE = dates.format_dates(BEST_DATE_INPUT)

STUDS_IKTA_21 = [
	"Бойко Божена КБ-305",
	"Гандзюк Владислав КБ-111",
	"Олійник Вікторію КІ-207",
	"Мартинюк Дмитро КБ-406",
	"Кицмен Євгеній КІ-201",
	"Пидорич Нікіта КБ-109",
	"Козловська Катерина ІР-21",
	"Вотусь Ганна ІР-22",
	"Даніїл Душинський КІ-406",
	"Ігор Лінчевський КІ-406",
	"Матусевич Ярослав ІР-14",
	"Біляк Діана ІР-14",
	"Козак Владислав ІР-14",
	"Шубіна Надія КІ-108",
	"Марцінковський Степан ІР-31",
	"Скарбарчук Денис КІ-107",
	"Ільєв Ілля КІ-409",
	"Кіріл Омельченко ІР-12",
	"Вишніцький Андрій ІВ-12",
	"Віталій Чемерис ІВ-12",
	"Сергієнко Владислав КІ-103",
]

STUDS_IKNI_37 = [
	"Лисяк Яніна СА-32",
	"Олефір Ксенія ПЗ-44",
	"Лукащик Діана ПЗ-27",
	"Журба Софія ПЗ-22",
	"Клименко Нікіта ITIC-11",
	"Д’яченко Назар ОІ-31",
	"Морозова Анна ПЗ-32",
	"Бідун Ольга СА-13",
	"Вац Каміла ПП-23",
	"Ковель Олексій ПП-23",
	"Мінчак Ярина ФЛ-16",
	"Мацевич Назар ШІ-24",
	"Тимейчук Максим ШІ-24",
	"Іванюк Арсен ОІ-14",
	"Доценко Софія ВР-11",
	"Щевчук Дем’ян ВР-13",
	"Ярко Захар ПП-45",
	"Рубан Лев ПЗ-13",
	"Думанська Наталія ПЗ-33",
	"Котюк Софія ПЗ-32",
	"Федорінін Олександр ОІ-45",
	"Сеник Денис ПЗ-13",
	"Опришко Юрій ПЗ-13",
	"Соколов Назар ПЗ-13",
	"Нікіфореску Марк-Тіберій ПЗ-13",
	"Калюк Ілля ПЗ-13",
	"Процик Юрій ПЗ-13",
	"Наврощук Арсен ПЗ-37",
	"Карабінович Василь ПП-36",
	"Дем’яненко Андрій ПЗ-34",
	"Мєдєнцов Валентин ПЗ-31",
	"Лотоцький Віталій ПЗ-36",
	"Намофілов Владислав ПЗ-35",
	"Волик Олексій ПП-15",
	"Пивнюк Микола ПП-15",
	"Кирил Чуєнко ПП-15",
	"Девдюк Стас ОІ-11",
]

STUDS_IBIB_4 = [
	"Андрій Федик БД-206",
	"Тетяна Постол БД-107",
	"Олексій Концур БД-102",
	"Владислав Теслюк БД-118",
]

STUDS_IARD_4 = [
	"Олександра Філоненко АР-106",
	"Марія Яводчак АР-117",
	"Уляна Малину АР-301",
	"Марія Мельничук АР-204",
]


def make_spec(tid: str, a: dict[str, Any]) -> dict[str, Any]:
	return templates.build_spec(tid, a)


def absence_answers(
	inst: str, studs: list[str], *, in_appendix: str | None = None
) -> dict[str, Any]:
	ans: dict[str, Any] = {
		"inst": inst,
		"date": BEST_DATE,
		"_dates": [
			[s.isoformat(), e.isoformat()] for s, e in dates.parse_dates(BEST_DATE_INPUT)
		],
		"reason": BEST_REASON,
		"students": studs,
	}
	if in_appendix is not None:
		ans["in_appendix"] = in_appendix
	return ans


def assert_clean_check(
	tid: str, a: dict[str, Any], spec: dict[str, Any], data: bytes
) -> None:
	issues = validator.check(tid, a, spec, today=REF_TODAY)
	assert not any(lv in ("err", "warn") for lv, _ in issues), issues
	rep = validator.check_docx(data, today=REF_TODAY)
	assert "Знайшов клопотань: <b>1</b>" in rep[0], rep
	assert not any("❌" in line or "⚠️" in line for line in rep), rep


def assert_indented_list(p: Any, indent_cm: float = 1.27, *, keep: bool | None) -> None:
	pf = p.paragraph_format
	assert pf.line_spacing == 1.15
	assert pf.left_indent is not None and abs(pf.left_indent - Cm(indent_cm)) < Cm(0.01)
	assert not pf.first_line_indent
	assert pf.keep_with_next is keep
	assert p.runs[0].font.name == "Times New Roman"
	assert p.runs[0].font.size == Pt(14)


def make_fake_bot_harness(start_mid: int = 100) -> tuple[Any, ...]:
	from aiogram import Bot, Dispatcher
	from aiogram.client.default import DefaultBotProperties
	from aiogram.client.session.base import BaseSession
	from aiogram.enums import ParseMode
	from aiogram.fsm.storage.base import StorageKey
	from aiogram.fsm.storage.memory import MemoryStorage
	from aiogram.methods import (
		AnswerCallbackQuery,
		EditMessageCaption,
		EditMessageReplyMarkup,
		EditMessageText,
		SendDocument,
		SendMessage,
	)
	from aiogram.types import (
		CallbackQuery,
		Chat,
		InlineKeyboardMarkup,
		Message,
		Update,
		User,
	)

	from app import bot as bot_mod

	class FakeSession(BaseSession):
		def __init__(self) -> None:
			super().__init__()
			self.calls: list[Any] = []
			self.next_mid = start_mid

		async def make_request(
			self, bot: Bot, method: Any, timeout: int | None = None
		) -> Any:
			self.calls.append(method)
			if isinstance(method, SendMessage):
				assert method.chat_id is not None
				self.next_mid += 1
				markup = (
					method.reply_markup
					if isinstance(method.reply_markup, InlineKeyboardMarkup)
					else None
				)
				return Message(
					message_id=self.next_mid,
					date=datetime.now(UTC),
					chat=Chat(id=int(method.chat_id), type="private"),
					text=method.text,
					reply_markup=markup,
				)
			if isinstance(method, EditMessageText):
				assert method.message_id is not None and method.chat_id is not None
				markup = (
					method.reply_markup
					if isinstance(method.reply_markup, InlineKeyboardMarkup)
					else None
				)
				return Message(
					message_id=int(method.message_id),
					date=datetime.now(UTC),
					chat=Chat(id=int(method.chat_id), type="private"),
					text=method.text,
					reply_markup=markup,
				)
			if isinstance(method, EditMessageCaption):
				assert method.message_id is not None and method.chat_id is not None
				markup = (
					method.reply_markup
					if isinstance(method.reply_markup, InlineKeyboardMarkup)
					else None
				)
				return Message(
					message_id=int(method.message_id),
					date=datetime.now(UTC),
					chat=Chat(id=int(method.chat_id), type="private"),
					caption=method.caption,
					reply_markup=markup,
				)
			if isinstance(method, SendDocument):
				assert method.chat_id is not None
				self.next_mid += 1
				markup = (
					method.reply_markup
					if isinstance(method.reply_markup, InlineKeyboardMarkup)
					else None
				)
				return Message(
					message_id=self.next_mid,
					date=datetime.now(UTC),
					chat=Chat(id=int(method.chat_id), type="private"),
					caption=method.caption,
					reply_markup=markup,
				)
			return True

		async def close(self) -> None:
			return None

		async def stream_content(
			self,
			url: str,
			headers: dict[str, Any] | None = None,
			timeout: int = 30,
			chunk_size: int = 65536,
			raise_for_status: bool = True,
		) -> AsyncGenerator[bytes, None]:
			if False:
				yield b""

	session = FakeSession()
	bot = Bot(
		"42:TEST_TOKEN",
		session=session,
		default=DefaultBotProperties(parse_mode=ParseMode.HTML),
	)
	storage = MemoryStorage()
	dp = Dispatcher(storage=storage)
	dp.callback_query.middleware(bot_mod.StaleGuard())
	dp.include_router(bot_mod.router)
	return (
		session,
		bot,
		storage,
		dp,
		StorageKey,
		CallbackQuery,
		Chat,
		Message,
		Update,
		User,
		(
			SendMessage,
			EditMessageText,
			EditMessageReplyMarkup,
			AnswerCallbackQuery,
			SendDocument,
		),
	)
