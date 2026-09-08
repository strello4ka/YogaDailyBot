"""Локальные проверки меню: Telegram и база заменены заглушками."""

import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.bot_commands import setup_bot_commands
from app.handlers import help as help_handlers
from app.keyboards import get_completed_practice_keyboard

fake_db = types.ModuleType("data.db")
fake_db.get_user_bot_mode = Mock(return_value="daily")
fake_db.get_last_published_challenge_schedule = Mock(return_value=None)
with patch.dict(sys.modules, {"data.db": fake_db}):
    schedule = importlib.import_module("app.handlers.schedule")
    reply_handlers = importlib.import_module("app.handlers.reply_handlers")


class NewMenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.message = types.SimpleNamespace(reply_text=AsyncMock())
        self.query = types.SimpleNamespace(data="", answer=AsyncMock())
        self.update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            effective_message=self.message,
            callback_query=self.query,
        )
        self.context = types.SimpleNamespace(user_data={})

    async def test_commands_order(self):
        bot = types.SimpleNamespace(set_my_commands=AsyncMock())
        await setup_bot_commands(types.SimpleNamespace(bot=bot))
        commands = bot.set_my_commands.await_args.args[0]
        self.assertEqual([c.command for c in commands],
                         ["donate", "schedule", "favorite", "progress", "practice", "help"])
        self.assertEqual(commands[0].description, "Управление подпиской")

    def test_done_button_becomes_disabled(self):
        markup = get_completed_practice_keyboard(11, False, "yoga").to_dict()
        done = markup["inline_keyboard"][0][1]
        self.assertEqual(done["text"], "✅ Я сделал!")
        self.assertEqual(done["disabled"], {})
        self.assertNotIn("callback_data", done)

    async def test_practice_hint_with_video(self):
        self.message.reply_video = AsyncMock()
        self.context.bot_data = {"practice_keyboard_tutorial_video": "test-video-id"}
        await reply_handlers.get_practice_command(self.update, self.context)
        self.message.reply_video.assert_awaited_once_with(
            video="test-video-id", caption=reply_handlers.PRACTICE_KEYBOARD_HINT)
        self.message.reply_text.assert_not_awaited()

    async def test_practice_hint_without_video(self):
        self.context.bot_data = {}
        await reply_handlers.get_practice_command(self.update, self.context)
        self.message.reply_text.assert_awaited_once_with(reply_handlers.PRACTICE_KEYBOARD_HINT)

    async def test_filters_work_for_all_active_internal_modes(self):
        self.update.message = types.SimpleNamespace(text="Ленивые дни")
        for mode in ("by_mood", "daily", "challenge", "pending"):
            with patch.object(reply_handlers, "get_user_bot_mode", return_value=mode), \
                    patch.object(reply_handlers, "_dispatch_by_mood_button", new_callable=AsyncMock) as dispatch:
                await reply_handlers.handle_reply_button(self.update, self.context)
            self.assertEqual(dispatch.await_count, 0 if mode == "pending" else 1)

    async def test_help_parent(self):
        await help_handlers.help_command(self.update, self.context)
        call = self.message.reply_text.await_args
        self.assertIn("пиши @strello4ka.", call.args[0])
        self.assertEqual([row[0].text for row in call.kwargs["reply_markup"].inline_keyboard],
                         ["Частые вопросы", "Советы", "Порекомендовать практику"])

    async def test_faq_without_fifth_item(self):
        self.query.data = "help_faq"
        await help_handlers.help_section_callback(self.update, self.context)
        self.query.answer.assert_awaited_once()
        text = self.message.reply_text.await_args.args[0]
        self.assertIn("4. Как порекомендовать", text)
        self.assertNotIn("5.", text)
        self.assertNotIn("t.me/", text)

    async def test_help_delegates_existing_functions(self):
        for action, module_name, handler_name in (
            ("help_tips", "app.daily.tips", "handle_tips_callback"),
            ("help_suggest", "app.handlers.suggest_practice", "handle_suggest_practice_callback"),
        ):
            handler = AsyncMock()
            module = types.ModuleType(module_name)
            setattr(module, handler_name, handler)
            self.query.data = action
            with patch.dict(sys.modules, {module_name: module}):
                await help_handlers.help_section_callback(self.update, self.context)
            handler.assert_awaited_once_with(self.update, self.context)

    async def test_schedule_visibility_by_mode(self):
        for mode in ("pending", "by_mood", "daily", "challenge"):
            with patch.object(schedule, "get_user_bot_mode", return_value=mode):
                await schedule.schedule_command(self.update, self.context)
            buttons = self.message.reply_text.await_args.kwargs["reply_markup"].inline_keyboard
            self.assertEqual(len(buttons), 3 if mode == "challenge" else 2)

    async def test_old_challenge_button_denied_after_exit(self):
        self.query.data = "schedule_challenge"
        with patch.object(schedule, "get_user_bot_mode", return_value="daily"), \
                patch.object(schedule, "get_last_published_challenge_schedule") as load:
            await schedule.schedule_callback(self.update, self.context)
        load.assert_not_called()
        self.message.reply_text.assert_not_awaited()
        self.assertTrue(self.query.answer.await_args.kwargs["show_alert"])

    async def test_last_publication_is_sent_verbatim(self):
        self.query.data = "schedule_challenge"
        published = "📅 Расписание на неделю:\n\n*🌀Пн: 12 мин*\nПрактика\nКанал"
        with patch.object(schedule, "get_user_bot_mode", return_value="challenge"), \
                patch.object(schedule, "get_last_published_challenge_schedule", return_value=published):
            await schedule.schedule_callback(self.update, self.context)
        self.message.reply_text.assert_awaited_once_with(published, parse_mode="Markdown")

    async def test_no_publication(self):
        self.query.data = "schedule_challenge"
        with patch.object(schedule, "get_user_bot_mode", return_value="challenge"), \
                patch.object(schedule, "get_last_published_challenge_schedule", return_value=None):
            await schedule.schedule_callback(self.update, self.context)
        self.message.reply_text.assert_awaited_once_with("Расписание челленджа пока не опубликовано.")

    async def test_schedule_delegates_existing_functions(self):
        for action, module_name, handler_name in (
            ("schedule_time", "app.daily.set_time", "handle_set_time_callback"),
            ("schedule_pause", "app.daily.pause", "pause_toggle_command"),
        ):
            handler = AsyncMock()
            module = types.ModuleType(module_name)
            setattr(module, handler_name, handler)
            self.query.data = action
            with patch.dict(sys.modules, {module_name: module}):
                await schedule.schedule_callback(self.update, self.context)
            handler.assert_awaited_once_with(self.update, self.context)


if __name__ == "__main__":
    unittest.main()
