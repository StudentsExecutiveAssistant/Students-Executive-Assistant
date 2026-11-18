"""Інтеграційні тести FSM-сценаріїв Telegram-бота в пам'яті."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

from app import bot as bot_mod
from app import config
from app.core.cleaners import parse_user_ids
from tests.helpers import (
	BEST_REASON,
	STUDS_IBIB_4,
	STUDS_IKNI_37,
	make_fake_bot_harness,
)


def test_parse_user_ids() -> None:
	assert parse_user_ids("1001, 1002; 1001\n-1003 1002") == [1001, 1002, -1003]
	for bad in ("", "   ", "abc", "1001 abc", "-", "--123"):
		try:
			parse_user_ids(bad)
		except ValueError:
			pass
		else:
			raise AssertionError(f"Expected ValueError for {bad!r}")


def test_bot_dmode_flow_in_memory() -> None:
	async def run() -> None:
		(
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
			methods,
		) = make_fake_bot_harness(100)
		SendMessage, EditMessageText, _, _, _ = methods
		uid = 777
		chat = Chat(id=uid, type="private")
		user = User(id=uid, is_bot=False, first_name="Test")
		update_id = 0

		def next_uid() -> int:
			nonlocal update_id
			update_id += 1
			return update_id

		def last_rendered() -> Any:
			for call in reversed(session.calls):
				if isinstance(call, (SendMessage, EditMessageText)):
					return call
			raise AssertionError("No rendered message")

		def rendered_text(call: Any) -> str:
			assert isinstance(call, (SendMessage, EditMessageText)) and call.text is not None
			return call.text

		def cb_data(call: Any) -> list[str]:
			assert isinstance(call.reply_markup, InlineKeyboardMarkup)
			return [
				b.callback_data
				for row in call.reply_markup.inline_keyboard
				for b in row
				if b.callback_data is not None
			]

		async def tap(data: str, mid: int) -> None:
			msg = Message(message_id=mid, date=datetime.now(UTC), chat=chat, text="x")
			cq = CallbackQuery(
				id=str(next_uid()), from_user=user, chat_instance="ci", message=msg, data=data
			)
			await dp.feed_update(bot, Update(update_id=next_uid(), callback_query=cq))

		async def send(text: str) -> None:
			msg = Message(
				message_id=next_uid() + 1000,
				date=datetime.now(UTC),
				chat=chat,
				from_user=user,
				text=text,
			)
			await dp.feed_update(bot, Update(update_id=next_uid(), message=msg))

		async def state_data() -> dict[str, Any]:
			return await storage.get_data(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))

		try:
			await tap("tpl:rooms", 1)
			await tap("c:0", (await state_data())["mid"])
			mid = (await state_data())["mid"]
			assert cb_data(last_rendered())[:3] == [
				"dmode:one",
				"dmode:period",
				"dmode:multi",
			], cb_data(last_rendered())

			await tap("dmode:one", mid)
			assert (await state_data())["dmode"] == "one"
			assert (await state_data())["mid"] == mid
			assert "Один день" in rendered_text(last_rendered())
			assert cb_data(last_rendered()) == ["dmode:back", "cancel"]

			await tap("dmode:back", mid)
			assert (await state_data())["dmode"] is None
			assert cb_data(last_rendered())[:3] == [
				"dmode:one",
				"dmode:period",
				"dmode:multi",
			]

			await tap("dmode:period", mid)
			assert (await state_data())["dmode"] == "period"
			assert "Період" in rendered_text(last_rendered())
			await tap("dmode:back", mid)

			await tap("dmode:multi", mid)
			assert (await state_data())["dmode"] == "multi"
			assert "16:00-20:30" in rendered_text(last_rendered())

			await send("26.11.2026 16:00-20:30\n28.11.2026 14:00-18:00")
			st = await state_data()
			assert st["dmode"] is None
			assert st["a"]["_timed"] is True
			assert st["a"]["_times"] == [[960, 1230], [840, 1080]]
			assert "Для чого?" in rendered_text(last_rendered())

			await send("проведення репетиції")
			await tap("skip", (await state_data())["mid"])
			assert (
				await storage.get_state(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
			) == bot_mod.Form.confirm.state

			await tap("edit", (await state_data())["mid"])
			await tap("e:1", (await state_data())["mid"])
			assert cb_data(last_rendered())[:3] == [
				"dmode:one",
				"dmode:period",
				"dmode:multi",
			]
			await send("26.11.2026")
			st = await state_data()
			assert "_timed" not in st["a"]
			assert "Година?" in rendered_text(last_rendered())

			await tap("tpl:absence", (await state_data())["mid"])
			await tap("i:ІКТА", (await state_data())["mid"])
			abs_mid = (await state_data())["mid"]
			await tap("dmode:multi", abs_mid)
			assert "16:00-20:30" not in rendered_text(last_rendered())
			await send("26.11.2026 16:00-20:30")
			assert "без годин" in rendered_text(last_rendered())

			await send("26.11.2026")
			await send("підготовкою до заходу")
			await send("\n".join(STUDS_IBIB_4))
			assert "Де розмістити список студентів?" in rendered_text(last_rendered())
			await tap("c:0", (await state_data())["mid"])
			assert (
				await storage.get_state(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
			) == bot_mod.Form.confirm.state
			pv_text = rendered_text(last_rendered())
			assert "Додаток 1" not in pv_text
			assert "Андрій Федик БД-206" in pv_text
			assert "Андрій Федик, БД-206" not in pv_text

			await tap("edit", (await state_data())["mid"])
			await tap("e:3", (await state_data())["mid"])
			await send("\n".join(STUDS_IKNI_37[:10]))
			assert (
				await storage.get_state(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
			) == bot_mod.Form.confirm.state
			st_abs10 = await state_data()
			assert "in_appendix" not in st_abs10["a"]
			assert "[Додаток 1: 10 студ.]" in rendered_text(last_rendered())

			await tap("edit", (await state_data())["mid"])
			await tap("e:3", (await state_data())["mid"])
			await send("\n".join(STUDS_IBIB_4[:3]))
			assert "Де розмістити список студентів?" in rendered_text(last_rendered())
			await tap("c:1", (await state_data())["mid"])
			assert (
				await storage.get_state(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
			) == bot_mod.Form.confirm.state
			assert "[Додаток 1: 3 студ.]" in rendered_text(last_rendered())

			await tap("tpl:award", (await state_data())["mid"])
			await tap("c:0", (await state_data())["mid"])
			await send("за активну громадську діяльність")
			await send(
				"Оршак Максим Олександрович\tІПМТ\tРК-31\nМірінчик Богдан Віталійович ІГСН аспірант"
			)
			assert (
				await storage.get_state(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
			) == bot_mod.Form.confirm.state
			st = await state_data()
			assert st["a"]["reason"] == "активну громадську діяльність"
			assert st["a"]["students"] == [
				["Оршак Максим Олександрович", "ІПМТ", "РК-31"],
				["Мірінчик Богдан Віталійович", "ІГСН", "аспірант"],
			]
			assert st["spec"]["addressee"] == config.ADDRESSEES["rector"][1]
			assert "Наталії ШАХОВСЬКІЙ" in rendered_text(last_rendered())

			await tap("tpl:audience", (await state_data())["mid"])
			await send("018")
			await tap("c:0", (await state_data())["mid"])
			await tap("c:2", (await state_data())["mid"])
			await tap("c:0", (await state_data())["mid"])
			await send("8:00-21:00")
			await send("проведення засідань")
			await tap("r:done", (await state_data())["mid"])
			await tap("skip", (await state_data())["mid"])
			await tap("skip", (await state_data())["mid"])
			await tap("c:1", (await state_data())["mid"])
			await tap("i:ІЕСК", (await state_data())["mid"])
			aud_preview = rendered_text(last_rendered())
			assert "Андрію МАЛЯРУ" in aud_preview
			assert "у будні дні протягом" in aud_preview
		finally:
			bot_mod.router._parent_router = None
			await bot.session.close()

	asyncio.run(run())


def test_dlya_parsing_and_resp_badges_in_memory() -> None:
	async def run() -> None:
		(
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
			methods,
		) = make_fake_bot_harness(500)
		SendMessage, EditMessageText, EditMessageReplyMarkup, AnswerCallbackQuery, _ = (
			methods
		)
		uid = 888
		chat = Chat(id=uid, type="private")
		user = User(id=uid, is_bot=False, first_name="Test")
		update_id = 0

		def next_uid() -> int:
			nonlocal update_id
			update_id += 1
			return update_id

		def last_rendered() -> Any:
			for call in reversed(session.calls):
				if isinstance(call, (SendMessage, EditMessageText, EditMessageReplyMarkup)):
					return call
			raise AssertionError("No rendered message")

		def last_text_msg() -> Any:
			for call in reversed(session.calls):
				if isinstance(call, (SendMessage, EditMessageText)) and call.text is not None:
					return call
			raise AssertionError("No text message")

		def btn_texts(call: Any) -> list[str]:
			assert isinstance(call.reply_markup, InlineKeyboardMarkup)
			return [b.text for row in call.reply_markup.inline_keyboard for b in row]

		def last_answer() -> Any:
			for call in reversed(session.calls):
				if isinstance(call, AnswerCallbackQuery):
					return call
			raise AssertionError("No AnswerCallbackQuery")

		async def tap(data: str, mid: int) -> None:
			msg = Message(message_id=mid, date=datetime.now(UTC), chat=chat, text="x")
			cq = CallbackQuery(
				id=str(next_uid()), from_user=user, chat_instance="ci", message=msg, data=data
			)
			await dp.feed_update(bot, Update(update_id=next_uid(), callback_query=cq))

		async def send(text: str) -> None:
			msg = Message(
				message_id=next_uid() + 1000,
				date=datetime.now(UTC),
				chat=chat,
				from_user=user,
				text=text,
			)
			await dp.feed_update(bot, Update(update_id=next_uid(), message=msg))

		async def state_data() -> dict[str, Any]:
			return await storage.get_data(StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))

		try:
			await tap("tpl:rooms", 1)
			await tap("c:0", (await state_data())["mid"])
			await send("26.11.2026 16:00-20:30")
			await send("для для проведення вечора")
			st = await state_data()
			assert st["a"]["purpose"] == "проведення вечора", st["a"]
			assert "прибрано зайве «для»" in st["a"].get("_fixes", []), st["a"]

			mid = st["mid"]
			await tap("rc:1", mid)
			await tap("rr:0", mid)
			await tap("rp:0", mid)
			await tap("rpok", mid)
			await tap("r:menu", mid)
			menu_btns = btn_texts(last_rendered())
			assert "🗂 Голови відділів (✅ 1)" in menu_btns, menu_btns
			assert "🏫 Профбюро інституту" in menu_btns, menu_btns

			await tap("rc:1", mid)
			role_btns = btn_texts(last_rendered())
			assert any(
				t.startswith("✅ Голова проєктного") and t.endswith("(1/1)") for t in role_btns
			), role_btns
			await tap("rr:0", mid)
			rpeople_msg = last_text_msg()
			assert rpeople_msg.text is not None
			assert "☑️ — вже додано у клопотання" in rpeople_msg.text
			assert "☑️ Гладчук Святослав (додано)" in btn_texts(rpeople_msg), btn_texts(
				rpeople_msg
			)

			parts_before = list((await state_data())["rs"]["parts"])
			await tap("rp:0", mid)
			assert "вже додано у клопотання" in (last_answer().text or "")
			assert (await state_data())["rs"]["parts"] == parts_before
			assert (await state_data())["rs"]["sel"] == []

			await tap("r:cat", mid)
			await tap("r:menu", mid)
			await tap("r:inst", mid)
			await tap("ri:ІКТА", mid)
			await tap("ip:0", mid)
			await tap("ipok", mid)
			await tap("r:menu", mid)
			assert "🏫 Профбюро інституту (✅ 1)" in btn_texts(last_rendered())
			await tap("r:inst", mid)
			assert "✅ ІКТА" in btn_texts(last_rendered()), btn_texts(last_rendered())
			await tap("ri:ІКТА", mid)
			ipeople_msg = last_text_msg()
			assert ipeople_msg.text is not None
			assert "☑️ — вже додано у клопотання" in ipeople_msg.text
			assert "☑️ Мельник Денис · Голова (додано)" in btn_texts(ipeople_msg), btn_texts(
				ipeople_msg
			)

			await tap("tpl:bus", mid)
			await send("для поїздки у Карпати")
			st_bus = await state_data()
			assert st_bus["a"]["route"] == "у Карпати", st_bus["a"]
			assert "прибрано зайве «для»" in st_bus["a"].get("_fixes", []), st_bus["a"]

			await tap("tpl:absence", (await state_data())["mid"])
			await tap("i:ІКНІ", (await state_data())["mid"])
			await send("23-27.10.2026")
			await send(f"з {BEST_REASON}")
			st_abs = await state_data()
			assert st_abs["a"]["reason"] == BEST_REASON, st_abs["a"]
			assert "прибрано зайве «з»" in st_abs["a"].get("_fixes", []), st_abs["a"]

			await tap("tpl:absence", (await state_data())["mid"])
			await tap("i:ІКНІ", (await state_data())["mid"])
			await send("23-27.10.2026")
			await send("у зв’язку з з організацією заходу")
			st_abs2 = await state_data()
			assert st_abs2["a"]["reason"] == "організацією заходу", st_abs2["a"]
			assert "прибрано зайве «у зв’язку з»" in st_abs2["a"].get("_fixes", []), st_abs2[
				"a"
			]
		finally:
			bot_mod.router._parent_router = None
			await bot.session.close()

	asyncio.run(run())


def test_admin_flow_in_memory() -> None:
	async def run() -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			old_admins_file = config.ADMINS_FILE
			old_last_file = config.LAST_USED_FILE
			config.ADMINS_FILE = os.path.join(tmpdir, "admins.json")
			config.LAST_USED_FILE = os.path.join(tmpdir, "last_used.json")
			(
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
				methods,
			) = make_fake_bot_harness(900)
			from aiogram.types import Document as TgDocument

			SendMessage, EditMessageText, _, AnswerCallbackQuery, SendDocument = methods

			admin1_uid = 1001
			admin2_uid = 1002
			admin3_uid = 3003
			student_uid = 2002
			config.add_admin_id(admin1_uid)
			config.add_admin_id(admin2_uid)
			assert json.loads(Path(config.ADMINS_FILE).read_text(encoding="utf-8")) == {
				"admins": [1001, 1002]
			}
			assert config.all_admin_ids() == {1001, 1002}

			admin1_chat = Chat(id=admin1_uid, type="private")
			admin1_user = User(id=admin1_uid, is_bot=False, first_name="Богдан")
			stud_chat = Chat(id=student_uid, type="private")
			stud_user = User(
				id=student_uid, is_bot=False, first_name="Святослав", username="sviatoslav"
			)
			update_id = 0

			def next_uid() -> int:
				nonlocal update_id
				update_id += 1
				return update_id

			def last_rendered_for(uid: int) -> Any:
				for call in reversed(session.calls):
					if (
						isinstance(call, (SendMessage, EditMessageText))
						and call.chat_id is not None
						and int(call.chat_id) == uid
					):
						return call
				raise AssertionError(f"No rendered message for {uid}")

			def rendered_text_for(uid: int) -> str:
				call = last_rendered_for(uid)
				assert call.text is not None
				return call.text

			def last_answer() -> Any:
				for call in reversed(session.calls):
					if isinstance(call, AnswerCallbackQuery):
						return call
				raise AssertionError("No AnswerCallbackQuery")

			def cb_data(call: Any) -> list[str]:
				if not isinstance(call.reply_markup, InlineKeyboardMarkup):
					return []
				return [
					b.callback_data
					for row in call.reply_markup.inline_keyboard
					for b in row
					if b.callback_data is not None
				]

			async def send_as(u: Any, ch: Any, text: str) -> None:
				msg = Message(
					message_id=next_uid() + 2000,
					date=datetime.now(UTC),
					chat=ch,
					from_user=u,
					text=text,
				)
				await dp.feed_update(bot, Update(update_id=next_uid(), message=msg))

			async def send_doc_as(
				u: Any, ch: Any, data: bytes, filename: str = "check.docx"
			) -> None:
				doc_obj = TgDocument(
					file_id="doc-1",
					file_unique_id="doc-u1",
					file_name=filename,
					file_size=len(data),
				)
				msg = Message(
					message_id=next_uid() + 2000,
					date=datetime.now(UTC),
					chat=ch,
					from_user=u,
					document=doc_obj,
				)

				async def _fake_download(_file: Any, destination: Any, **_kw: Any) -> None:
					destination.write(data)

				with patch.object(bot, "download", _fake_download):
					await dp.feed_update(bot, Update(update_id=next_uid(), message=msg))

			async def tap_as(u: Any, ch: Any, data: str, mid: int) -> None:
				msg = Message(message_id=mid, date=datetime.now(UTC), chat=ch, text="x")
				cq = CallbackQuery(
					id=str(next_uid()), from_user=u, chat_instance="ci", message=msg, data=data
				)
				await dp.feed_update(bot, Update(update_id=next_uid(), callback_query=cq))

			async def state_mid(uid: int) -> int:
				data = await storage.get_data(
					StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
				)
				return int(data["mid"])

			async def create_rooms_petition(u: Any, ch: Any) -> None:
				await tap_as(u, ch, "tpl:rooms", 1)
				await tap_as(u, ch, "c:0", await state_mid(u.id))
				await send_as(u, ch, "26.11.2026 16:00-20:30")
				await send_as(u, ch, "проведення кіновечора")
				mid = await state_mid(u.id)
				await tap_as(u, ch, "rc:1", mid)
				await tap_as(u, ch, "rr:0", mid)
				await tap_as(u, ch, "rp:0", mid)
				await tap_as(u, ch, "rpok", mid)
				await tap_as(u, ch, "r:done", mid)
				await tap_as(u, ch, "make", await state_mid(u.id))

			try:
				await send_as(stud_user, stud_chat, "/start")
				assert "/admins" not in rendered_text_for(student_uid)
				await send_as(admin1_user, admin1_chat, "/start")
				assert "/admins" not in rendered_text_for(admin1_uid)
				await send_as(admin1_user, admin1_chat, "/help")
				help_txt = rendered_text_for(admin1_uid)
				assert "/admins" not in help_txt
				assert "Надіслати за User ID" not in help_txt

				before_docs = len(session.calls)
				await create_rooms_petition(stud_user, stud_chat)
				stud_make_docs = [
					c for c in session.calls[before_docs:] if isinstance(c, SendDocument)
				]
				docs_by_chat = {int(c.chat_id): c for c in stud_make_docs}
				assert set(docs_by_chat) == {student_uid, admin1_uid, admin2_uid}

				stud_doc = docs_by_chat[student_uid]
				assert isinstance(stud_doc.document, BufferedInputFile)
				stud_bytes = stud_doc.document.data
				assert stud_bytes[:2] == b"PK"
				assert "Готово ✅" in (stud_doc.caption or "")
				assert "Копію надіслано адмінам." in (stud_doc.caption or "")
				assert "send:ask" not in cb_data(last_rendered_for(student_uid))

				for a_uid in (admin1_uid, admin2_uid):
					adm_doc = docs_by_chat[a_uid]
					assert isinstance(adm_doc.document, BufferedInputFile)
					assert adm_doc.document.data == stud_bytes
					assert "Нове клопотання" in (adm_doc.caption or "")
					assert "Святослав" in (adm_doc.caption or "")
					assert "@sviatoslav" in (adm_doc.caption or "")
					assert str(student_uid) in (adm_doc.caption or "")

				await send_as(stud_user, stud_chat, "/admins")
				assert "Доступно лише адміністраторам" in rendered_text_for(student_uid)
				await tap_as(stud_user, stud_chat, "adm:list", 1)
				assert "Доступно лише адміністраторам" in (last_answer().text or "")

				before_admin_docs = len(session.calls)
				await create_rooms_petition(admin1_user, admin1_chat)
				adm_make_docs = [
					c for c in session.calls[before_admin_docs:] if isinstance(c, SendDocument)
				]
				adm_docs_by_chat = {int(c.chat_id): c for c in adm_make_docs}
				assert set(adm_docs_by_chat) == {admin1_uid, admin2_uid}
				assert "Готово ✅" in (adm_docs_by_chat[admin1_uid].caption or "")
				assert "Нове клопотання" in (adm_docs_by_chat[admin2_uid].caption or "")
				assert str(admin1_uid) in (adm_docs_by_chat[admin2_uid].caption or "")
				assert "send:ask" not in cb_data(last_rendered_for(admin1_uid))

				await send_doc_as(admin1_user, admin1_chat, stud_bytes)
				assert "Знайшов клопотань" in rendered_text_for(admin1_uid)
				assert "send:ask" not in cb_data(last_rendered_for(admin1_uid))

				await send_as(admin1_user, admin1_chat, "/admins")
				await tap_as(admin1_user, admin1_chat, "adm:add", 1)
				await send_as(admin1_user, admin1_chat, str(admin3_uid))
				await tap_as(admin1_user, admin1_chat, f"adm:del:{admin2_uid}", 1)
				assert config.all_admin_ids() == {admin1_uid, admin3_uid}
				assert json.loads(Path(config.ADMINS_FILE).read_text(encoding="utf-8")) == {
					"admins": [1001, 3003]
				}

				await tap_as(admin1_user, admin1_chat, f"adm:del:{admin3_uid}", 1)
				assert config.all_admin_ids() == {admin1_uid}
				assert f"adm:del:{admin1_uid}" not in cb_data(last_rendered_for(admin1_uid))
				await tap_as(admin1_user, admin1_chat, f"adm:del:{admin1_uid}", 1)
				assert config.all_admin_ids() == {admin1_uid}
				assert "єдиного адміністратора" in (last_answer().text or "")

				# Порожній admins.json має закривати доступ (fail-closed).
				Path(config.ADMINS_FILE).write_text('{"admins": []}', encoding="utf-8")
				assert config.is_admin(admin1_uid) is False
				assert config.is_admin(None) is False

				await tap_as(stud_user, stud_chat, "tpl:rooms", 1)
				await tap_as(stud_user, stud_chat, "c:0", await state_mid(student_uid))
				await send_as(stud_user, stud_chat, "26.11.2026 16:00-20:30")
				await send_as(stud_user, stud_chat, "проведення заходу")
				Path(config.LAST_USED_FILE).unlink(missing_ok=True)
				await tap_as(stud_user, stud_chat, "r:last", await state_mid(student_uid))
				assert "Немає збереженого вибору" in (last_answer().text or "")
				await tap_as(stud_user, stud_chat, "r:done", await state_mid(student_uid))
				await tap_as(stud_user, stud_chat, "more", await state_mid(student_uid))
				st_more = await storage.get_data(
					StorageKey(bot_id=bot.id, chat_id=student_uid, user_id=student_uid)
				)
				assert len(st_more.get("batch", [])) == 1
				await send_as(stud_user, stud_chat, "/new")
				st_new = await storage.get_data(
					StorageKey(bot_id=bot.id, chat_id=student_uid, user_id=student_uid)
				)
				assert st_new == {}

				await tap_as(stud_user, stud_chat, "tpl:purchase", 1)
				await tap_as(stud_user, stud_chat, "c:0", await state_mid(student_uid))
				await send_as(stud_user, stud_chat, "з метою проведення студентських подій")
				await send_as(stud_user, stud_chat, "Мікрофон; 1; 1000")
				await tap_as(stud_user, stud_chat, "skip", await state_mid(student_uid))
				await tap_as(stud_user, stud_chat, "edit", await state_mid(student_uid))
				await tap_as(stud_user, stud_chat, "e:0", await state_mid(student_uid))
				await tap_as(stud_user, stud_chat, "c:0", await state_mid(student_uid))
				st_pur = await storage.get_data(
					StorageKey(bot_id=bot.id, chat_id=student_uid, user_id=student_uid)
				)
				assert st_pur["a"].get("goal") == "проведення студентських подій" or (
					"проведення студентських подій" in st_pur["a"].get("goal", "")
				)
			finally:
				config.ADMINS_FILE = old_admins_file
				config.LAST_USED_FILE = old_last_file
				bot_mod.router._parent_router = None
				await bot.session.close()

	asyncio.run(run())
