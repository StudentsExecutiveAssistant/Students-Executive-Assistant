"""Інтеграційні тести фідбеку в пам'яті: ексклюзивне взяття адміном, відпускання та одноразова відповідь."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiogram.types import InlineKeyboardMarkup

from app import bot as bot_mod
from app import config
from app.bot.handlers import feedback as fb_mod
from app.bot.states import Form
from tests.helpers import make_fake_bot_harness


def test_feedback_flow_in_memory() -> None:
	async def run() -> None:
		with tempfile.TemporaryDirectory() as tmp:
			old_admins_file = config.ADMINS_FILE
			config.ADMINS_FILE = Path(tmp) / "admins.json"
			admin1_uid, admin2_uid, student_uid = 1001, 2002, 5005
			config.ADMINS_FILE.write_text(
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
			) = make_fake_bot_harness(400)
			SendMessage, EditMessageText, _, AnswerCallbackQuery, _ = methods

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

			def last_rendered_for(chat_id: int) -> Any:
				for call in reversed(session.calls):
					if (
						isinstance(call, (SendMessage, EditMessageText))
						and int(call.chat_id) == chat_id
					):
						return call
				raise AssertionError(f"No rendered message for {chat_id}")

			def last_edit_for(chat_id: int, message_id: int) -> Any:
				for call in reversed(session.calls):
					if (
						isinstance(call, EditMessageText)
						and int(call.chat_id) == chat_id
						and int(call.message_id) == message_id
					):
						return call
				raise AssertionError(f"No edit for {chat_id}/{message_id}")

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
					message_id=next_uid() + 3000,
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

			async def get_state(uid: int) -> str | None:
				return await storage.get_state(
					StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
				)

			async def get_data(uid: int) -> dict[str, Any]:
				return await storage.get_data(
					StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid)
				)

			try:
				fb_mod.reset_tickets()

				await send_as(stud_user, stud_chat, "/start")
				assert "fb:new" in cb_data(last_rendered_for(student_uid))
				await send_as(stud_user, stud_chat, "/help")
				assert "/feedback" in (last_rendered_for(student_uid).text or "")

				await tap_as(stud_user, stud_chat, "fb:new", 1)
				assert await get_state(student_uid) == Form.feedback.state
				prompt_mid = int((await get_data(student_uid))["mid"])
				await tap_as(stud_user, stud_chat, "fb:cancel", prompt_mid)
				assert await get_state(student_uid) is None
				assert "Скасовано" in (last_rendered_for(student_uid).text or "")
				assert "fb:new" in cb_data(last_rendered_for(student_uid))

				await send_as(stud_user, stud_chat, "/feedback")
				assert await get_state(student_uid) == Form.feedback.state
				await send_as(
					stud_user, stud_chat, "Додайте, будь ласка, шаблон для гуртожитку!"
				)
				assert await get_state(student_uid) is None
				assert "надіслано адміністраторам" in (
					last_rendered_for(student_uid).text or ""
				)
				assert len(fb_mod._TICKETS) == 1
				ticket1 = next(iter(fb_mod._TICKETS.values()))
				tid1 = ticket1.ticket_id
				assert set(ticket1.admin_messages) == {admin1_uid, admin2_uid}
				assert cb_data(last_rendered_for(admin1_uid)) == [f"fb:take:{tid1}"]
				assert cb_data(last_rendered_for(admin2_uid)) == [f"fb:take:{tid1}"]
				assert "шаблон для гуртожитку" in (last_rendered_for(admin1_uid).text or "")
				# Перевіряємо, що фідбеки живуть лише в RAM і не пишуться на диск.
				assert list(Path(tmp).iterdir()) == [config.ADMINS_FILE]

				await tap_as(stud_user, stud_chat, f"fb:take:{tid1}", 1)
				assert "Доступно лише адміністраторам" in (last_answer().text or "")
				assert ticket1.claimed_by is None

				await tap_as(
					admin1_user,
					admin1_chat,
					f"fb:take:{tid1}",
					ticket1.admin_messages[admin1_uid],
				)
				assert ticket1.claimed_by == admin1_uid
				assert await get_state(admin1_uid) == Form.feedback_reply.state
				assert cb_data(last_rendered_for(admin1_uid)) == [f"fb:release:{tid1}"]
				assert "Ви взяли цей фідбек" in (last_rendered_for(admin1_uid).text or "")
				assert cb_data(last_rendered_for(admin2_uid)) == []
				assert "Взяв у роботу" in (last_rendered_for(admin2_uid).text or "")
				assert "Олена" in (last_rendered_for(admin2_uid).text or "")

				await tap_as(
					admin2_user,
					admin2_chat,
					f"fb:take:{tid1}",
					ticket1.admin_messages[admin2_uid],
				)
				assert "вже взяв інший адміністратор" in (last_answer().text or "")
				await tap_as(
					admin2_user,
					admin2_chat,
					f"fb:release:{tid1}",
					ticket1.admin_messages[admin2_uid],
				)
				assert "лише той адміністратор" in (last_answer().text or "")
				assert ticket1.claimed_by == admin1_uid

				await tap_as(stud_user, stud_chat, "fb:new", 2)
				await send_as(stud_user, stud_chat, "Друге повідомлення з фідбеком")
				assert len(fb_mod._TICKETS) == 2
				ticket2 = next(t for tid, t in fb_mod._TICKETS.items() if tid != tid1)
				tid2 = ticket2.ticket_id

				await tap_as(
					admin1_user,
					admin1_chat,
					f"fb:take:{tid2}",
					ticket2.admin_messages[admin1_uid],
				)
				assert "вже є активний фідбек" in (last_answer().text or "")
				assert ticket2.claimed_by is None

				await tap_as(admin1_user, admin1_chat, "fb:new", 3)
				assert "Спочатку дайте відповідь" in (last_answer().text or "")

				await tap_as(
					admin1_user,
					admin1_chat,
					f"fb:release:{tid1}",
					ticket1.admin_messages[admin1_uid],
				)
				assert ticket1.claimed_by is None
				assert await get_state(admin1_uid) is None
				assert cb_data(last_rendered_for(admin1_uid)) == [f"fb:take:{tid1}"]
				assert cb_data(last_rendered_for(admin2_uid)) == [f"fb:take:{tid1}"]

				await tap_as(
					admin2_user,
					admin2_chat,
					f"fb:take:{tid1}",
					ticket1.admin_messages[admin2_uid],
				)
				assert ticket1.claimed_by == admin2_uid
				assert await get_state(admin2_uid) == Form.feedback_reply.state

				before_reply = len(session.calls)
				await send_as(admin2_user, admin2_chat, "Дякуємо! Додамо цього тижня.")
				assert tid1 not in fb_mod._TICKETS
				assert await get_state(admin2_uid) is None
				stud_msgs = [
					c
					for c in session.calls[before_reply:]
					if isinstance(c, SendMessage) and int(c.chat_id) == student_uid
				]
				assert len(stud_msgs) == 1
				assert "Відповідь адміністратора" in stud_msgs[0].text
				assert "Додамо цього тижня." in stud_msgs[0].text
				assert cb_data(last_rendered_for(admin1_uid)) == []
				assert "Відповів:" in (last_rendered_for(admin1_uid).text or "")
				assert "Максим" in (last_rendered_for(admin1_uid).text or "")
				assert "✅" in (last_rendered_for(admin2_uid).text or "")

				# Одноразова відповідь: наступне повідомлення адміна не має пересилатися студенту.
				before_extra = len(session.calls)
				await send_as(admin2_user, admin2_chat, "Ще одне повідомлення")
				extra_stud_msgs = [
					c
					for c in session.calls[before_extra:]
					if isinstance(c, SendMessage) and int(c.chat_id) == student_uid
				]
				assert extra_stud_msgs == []

				await tap_as(
					admin1_user,
					admin1_chat,
					f"fb:take:{tid2}",
					ticket2.admin_messages[admin1_uid],
				)
				assert ticket2.claimed_by == admin1_uid
				await send_as(admin1_user, admin1_chat, "/cancel")
				assert ticket2.claimed_by is None
				assert await get_state(admin1_uid) is None
				assert "повернуто іншим адміністраторам" in (
					last_rendered_for(admin1_uid).text or ""
				)
				assert cb_data(last_rendered_for(admin2_uid)) == [f"fb:take:{tid2}"]

				await tap_as(
					admin2_user,
					admin2_chat,
					f"fb:take:{tid2}",
					ticket2.admin_messages[admin2_uid],
				)
				await send_as(admin2_user, admin2_chat, "Відповідь на друге повідомлення")
				assert fb_mod._TICKETS == {}

				await send_as(stud_user, stud_chat, "/feedback")
				await send_as(stud_user, stud_chat, "Третє повідомлення")
				ticket3 = next(iter(fb_mod._TICKETS.values()))
				tid3 = ticket3.ticket_id

				await tap_as(admin1_user, admin1_chat, "tpl:rooms", 10)
				assert await get_state(admin1_uid) == Form.filling.state
				await tap_as(
					admin1_user,
					admin1_chat,
					f"fb:take:{tid3}",
					ticket3.admin_messages[admin1_uid],
				)
				assert "завершіть поточну дію" in (last_answer().text or "")
				assert ticket3.claimed_by is None
				assert await get_state(admin1_uid) == Form.filling.state
				await send_as(admin1_user, admin1_chat, "/cancel")

				await tap_as(
					admin2_user,
					admin2_chat,
					f"fb:take:{tid3}",
					ticket3.admin_messages[admin2_uid],
				)
				assert ticket3.claimed_by == admin2_uid
				await tap_as(admin1_user, admin1_chat, f"adm:del:{admin2_uid}", 20)
				assert ticket3.claimed_by is None
				assert admin2_uid not in ticket3.admin_messages
				t3_card = last_edit_for(admin1_uid, ticket3.admin_messages[admin1_uid])
				assert cb_data(t3_card) == [f"fb:take:{tid3}"]

				Path(config.ADMINS_FILE).write_text('{"admins": []}', encoding="utf-8")
				await tap_as(stud_user, stud_chat, "fb:new", 30)
				assert "немає доступних адміністраторів" in (last_answer().text or "")
			finally:
				fb_mod.reset_tickets()
				config.ADMINS_FILE = old_admins_file
				bot_mod.router._parent_router = None
				await bot.session.close()

	asyncio.run(run())
