"""Інтеграційні тести адмін-кнопок «Надруковано» і «Відмовлено» на створених клопотаннях."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiogram.methods import EditMessageCaption
from aiogram.types import InlineKeyboardMarkup

from app import bot as bot_mod
from app import config
from app.bot.handlers import petitions as pet_mod
from app.bot.states import Form
from tests.helpers import make_fake_bot_harness


def test_petition_review_buttons_flow_in_memory() -> None:
	async def run() -> None:
		with tempfile.TemporaryDirectory() as tmp:
			old_admins_file = config.ADMINS_FILE
			old_last_file = config.LAST_USED_FILE
			config.ADMINS_FILE = os.path.join(tmp, "admins.json")
			config.LAST_USED_FILE = os.path.join(tmp, "last_used.json")
			admin1_uid, admin2_uid, student_uid = 1001, 2002, 5005
			Path(config.ADMINS_FILE).write_text(
				json.dumps({"admins": [admin1_uid, admin2_uid]}), encoding="utf-8"
			)

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
			) = make_fake_bot_harness(700)
			SendMessage, _, _, AnswerCallbackQuery, SendDocument = methods

			admin1_user = User(
				id=admin1_uid, is_bot=False, first_name="Олена", username="olena_adm"
			)
			admin2_user = User(
				id=admin2_uid, is_bot=False, first_name="Максим", username="maks_adm"
			)
			stud_user = User(
				id=student_uid, is_bot=False, first_name="Іван", username="ivan_stud"
			)
			admin1_chat = Chat(id=admin1_uid, type="private")
			admin2_chat = Chat(id=admin2_uid, type="private")
			stud_chat = Chat(id=student_uid, type="private")
			update_id = 0

			def next_uid() -> int:
				nonlocal update_id
				update_id += 1
				return update_id

			def cb_data(call: Any) -> list[str]:
				if not isinstance(call.reply_markup, InlineKeyboardMarkup):
					return []
				return [
					b.callback_data
					for row in call.reply_markup.inline_keyboard
					for b in row
					if b.callback_data is not None
				]

			def last_answer() -> Any:
				for call in reversed(session.calls):
					if isinstance(call, AnswerCallbackQuery):
						return call
				raise AssertionError("No AnswerCallbackQuery")

			def last_caption_edit(chat_id: int, message_id: int) -> EditMessageCaption:
				for call in reversed(session.calls):
					if (
						isinstance(call, EditMessageCaption)
						and int(call.chat_id) == chat_id
						and int(call.message_id) == message_id
					):
						return call
				raise AssertionError(f"No EditMessageCaption for {chat_id}/{message_id}")

			def last_msg_for(chat_id: int) -> Any:
				for call in reversed(session.calls):
					if isinstance(call, SendMessage) and int(call.chat_id) == chat_id:
						return call
				raise AssertionError(f"No SendMessage for {chat_id}")

			async def send_as(u: Any, ch: Any, text: str) -> None:
				msg = Message(
					message_id=next_uid() + 4000,
					date=datetime.now(UTC),
					chat=ch,
					from_user=u,
					text=text,
				)
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

			async def get_state(uid: int) -> str | None:
				return await storage.get_state(
					StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
				)

			async def create_petition() -> pet_mod.PetitionReview:
				before = set(pet_mod._REVIEWS)
				await tap_as(stud_user, stud_chat, "tpl:rooms", 1)
				await tap_as(stud_user, stud_chat, "c:0", await state_mid(student_uid))
				await send_as(stud_user, stud_chat, "26.11.2026 16:00-20:30")
				await send_as(stud_user, stud_chat, "проведення кіновечора")
				await tap_as(stud_user, stud_chat, "skip", await state_mid(student_uid))
				await tap_as(stud_user, stud_chat, "make", await state_mid(student_uid))
				created = set(pet_mod._REVIEWS) - before
				assert len(created) == 1
				return pet_mod._REVIEWS[next(iter(created))]

			try:
				pet_mod.reset_reviews()

				# 1. Створення клопотання: адміни отримують документ із кнопками «Надруковано» і «Відмовлено».
				before_docs = len(session.calls)
				rev1 = await create_petition()
				rid1 = rev1.review_id
				sent_docs = [
					c for c in session.calls[before_docs:] if isinstance(c, SendDocument)
				]
				adm_docs = {
					int(c.chat_id): c for c in sent_docs if int(c.chat_id) != student_uid
				}
				assert set(adm_docs) == {admin1_uid, admin2_uid}
				for a_uid in (admin1_uid, admin2_uid):
					assert cb_data(adm_docs[a_uid]) == [
						f"pet:print:{rid1}",
						f"pet:reject:{rid1}",
					]

				# Не-адмін не може натискати кнопки.
				await tap_as(stud_user, stud_chat, f"pet:print:{rid1}", 1)
				assert "Доступно лише адміністраторам" in (last_answer().text or "")
				assert rid1 in pet_mod._REVIEWS

				# 2. Адмін 1 тисне «Надруковано»: автора сповіщено, підписи в обох адмінів оновлено, кнопки знято.
				before_print = len(session.calls)
				await tap_as(
					admin1_user,
					admin1_chat,
					f"pet:print:{rid1}",
					rev1.admin_messages[admin1_uid],
				)
				assert rid1 not in pet_mod._REVIEWS
				stud_notifs = [
					c
					for c in session.calls[before_print:]
					if isinstance(c, SendMessage) and int(c.chat_id) == student_uid
				]
				assert len(stud_notifs) == 1
				assert "надруковано" in stud_notifs[0].text.lower()

				e1 = last_caption_edit(admin1_uid, rev1.admin_messages[admin1_uid])
				e2 = last_caption_edit(admin2_uid, rev1.admin_messages[admin2_uid])
				assert "Надруковано" in (e1.caption or "") and cb_data(e1) == []
				assert (
					"Надруковано" in (e2.caption or "")
					and "Олена" in (e2.caption or "")
					and cb_data(e2) == []
				)

				# Повторне натискання іншим адміном не дублює сповіщення.
				await tap_as(
					admin2_user,
					admin2_chat,
					f"pet:reject:{rid1}",
					rev1.admin_messages[admin2_uid],
				)
				assert "вже оброблено" in (last_answer().text or "")

				# 3. Відмова: блокування, скасування кнопкою «Скасувати», потім відмова з довгою причиною.
				rev2 = await create_petition()
				rid2 = rev2.review_id
				await tap_as(
					admin1_user,
					admin1_chat,
					f"pet:reject:{rid2}",
					rev2.admin_messages[admin1_uid],
				)
				assert rev2.rejecting_by == admin1_uid
				assert await get_state(admin1_uid) == Form.petition_reject.state
				rej_e1 = last_caption_edit(admin1_uid, rev2.admin_messages[admin1_uid])
				rej_e2 = last_caption_edit(admin2_uid, rev2.admin_messages[admin2_uid])
				assert cb_data(rej_e1) == [f"pet:noreason:{rid2}", f"pet:cancel:{rid2}"]
				assert cb_data(rej_e2) == []
				assert "Оформлює відмову" in (rej_e2.caption or "")

				# Інший адмін не може ані надрукувати, ані відхилити, поки адмін 1 оформлює відмову.
				await tap_as(
					admin2_user,
					admin2_chat,
					f"pet:print:{rid2}",
					rev2.admin_messages[admin2_uid],
				)
				assert "оформлює відмову" in (last_answer().text or "")

				# Адмін 1 не може почати фідбек під час оформлення відмови.
				await tap_as(admin1_user, admin1_chat, "fb:new", 50)
				assert "завершіть або скасуйте відмову" in (last_answer().text or "")

				# Скасування кнопкою «Скасувати» повертає кнопки обом адмінам.
				await tap_as(
					admin1_user,
					admin1_chat,
					f"pet:cancel:{rid2}",
					rev2.admin_messages[admin1_uid],
				)
				assert rev2.rejecting_by is None
				assert await get_state(admin1_uid) is None
				assert cb_data(
					last_caption_edit(admin1_uid, rev2.admin_messages[admin1_uid])
				) == [f"pet:print:{rid2}", f"pet:reject:{rid2}"]
				assert cb_data(
					last_caption_edit(admin2_uid, rev2.admin_messages[admin2_uid])
				) == [f"pet:print:{rid2}", f"pet:reject:{rid2}"]

				# Адмін 2 бере відмову і вводить довгу причину (>300 символів).
				await tap_as(
					admin2_user,
					admin2_chat,
					f"pet:reject:{rid2}",
					rev2.admin_messages[admin2_uid],
				)
				long_reason = "Неправильно вказано дату заходу. " * 15
				before_rej = len(session.calls)
				await send_as(admin2_user, admin2_chat, long_reason)
				assert rid2 not in pet_mod._REVIEWS
				assert await get_state(admin2_uid) is None

				stud_rej_msgs = [
					c
					for c in session.calls[before_rej:]
					if isinstance(c, SendMessage) and int(c.chat_id) == student_uid
				]
				assert len(stud_rej_msgs) == 1
				assert "У клопотанні відмовлено" in stud_rej_msgs[0].text
				assert long_reason.strip() in stud_rej_msgs[0].text

				done_e1 = last_caption_edit(admin1_uid, rev2.admin_messages[admin1_uid])
				done_e2 = last_caption_edit(admin2_uid, rev2.admin_messages[admin2_uid])
				assert "Відмовлено" in (done_e1.caption or "")
				assert "Максим" in (done_e1.caption or "")
				assert len(done_e1.caption or "") < 1024
				assert "…" in (done_e1.caption or "")
				assert cb_data(done_e1) == [] and cb_data(done_e2) == []

				# 4. Відмова без причини кнопкою «Надіслати без причини».
				rev3 = await create_petition()
				rid3 = rev3.review_id
				await tap_as(
					admin1_user,
					admin1_chat,
					f"pet:reject:{rid3}",
					rev3.admin_messages[admin1_uid],
				)
				before_nr = len(session.calls)
				await tap_as(
					admin1_user,
					admin1_chat,
					f"pet:noreason:{rid3}",
					rev3.admin_messages[admin1_uid],
				)
				assert rid3 not in pet_mod._REVIEWS
				assert await get_state(admin1_uid) is None
				nr_msgs = [
					c
					for c in session.calls[before_nr:]
					if isinstance(c, SendMessage) and int(c.chat_id) == student_uid
				]
				assert len(nr_msgs) == 1
				assert "У клопотанні відмовлено" in nr_msgs[0].text
				assert "Причина:" not in nr_msgs[0].text

				# 5. Звільнення блокування через /cancel та при видаленні адміна.
				rev4 = await create_petition()
				rid4 = rev4.review_id
				await tap_as(
					admin1_user,
					admin1_chat,
					f"pet:reject:{rid4}",
					rev4.admin_messages[admin1_uid],
				)
				await send_as(admin1_user, admin1_chat, "/cancel")
				assert rev4.rejecting_by is None
				assert await get_state(admin1_uid) is None
				assert "Клопотання повернуто іншим адміністраторам" in (
					last_msg_for(admin1_uid).text or ""
				)

				await tap_as(
					admin2_user,
					admin2_chat,
					f"pet:reject:{rid4}",
					rev4.admin_messages[admin2_uid],
				)
				assert rev4.rejecting_by == admin2_uid
				await tap_as(admin1_user, admin1_chat, f"adm:del:{admin2_uid}", 20)
				assert rev4.rejecting_by is None
				assert admin2_uid not in rev4.admin_messages
				assert cb_data(
					last_caption_edit(admin1_uid, rev4.admin_messages[admin1_uid])
				) == [f"pet:print:{rid4}", f"pet:reject:{rid4}"]
			finally:
				pet_mod.reset_reviews()
				config.ADMINS_FILE = old_admins_file
				config.LAST_USED_FILE = old_last_file
				bot_mod.router._parent_router = None
				await bot.session.close()

	asyncio.run(run())
