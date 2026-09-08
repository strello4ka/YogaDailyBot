import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


fake_db = types.ModuleType("data.db")
fake_db.clear_user_challenge = lambda _user_id: True
fake_db.complete_user_challenge_setup = lambda *_args, **_kwargs: True
fake_db.get_current_weekday = lambda: 1
fake_db.start_user_challenge_setup = lambda *_args, **_kwargs: True
fake_db.is_user_onboarding_required = lambda _user_id: False
fake_db.PRACTICE_CATALOG_MOOD = "mood"
fake_db.PRACTICE_CATALOG_YOGA = "yoga"
fake_db.get_available_combined_difficulties = lambda *_args, **_kwargs: set()
fake_db.get_available_combined_tegs = lambda *_args, **_kwargs: set()
fake_db.pick_random_combined_mood_pool = lambda *_args, **_kwargs: None
sys.modules["data.db"] = fake_db

from app.challenge.flow import exit_flow, start_flow


class ChallengeNewScenarioTests(unittest.IsolatedAsyncioTestCase):
    def test_welcome_has_week_and_date(self):
        from datetime import date
        with patch.object(start_flow, "get_challenge_start_date", return_value=date(2026, 9, 14)):
            text = start_flow.build_challenge_welcome_text()
        self.assertIn("начиная с 14.09", text)
        self.assertIn("по воскресеньям - релакс", text)

    def test_finished_text_matches_new_interface(self):
        text = exit_flow.build_challenge_finished_text(17)
        self.assertIn("*17/28*", text)
        self.assertIn("управление подпиской", text)
        self.assertNotIn("Выбери, как дальше", text)

    async def test_finish_is_one_message_with_common_keyboard(self):
        bot = types.SimpleNamespace(send_message=AsyncMock())
        context = types.SimpleNamespace(bot=bot)
        fake_extra = types.ModuleType("app.daily.extra_practices")
        fake_extra.strip_extra_practices_inline_keyboards = AsyncMock()
        fake_done = types.ModuleType("app.handlers.done")
        fake_done.cancel_done_reminders = AsyncMock()
        fake_done.dismiss_done_reminders = lambda _user_id: None
        with patch.dict(sys.modules, {
            "app.daily.extra_practices": fake_extra,
            "app.handlers.done": fake_done,
        }):
            result = await exit_flow.finish_challenge_for_user(
                context, user_id=7, chat_id=70, completed=10)
        self.assertTrue(result)
        self.assertEqual(bot.send_message.await_count, 1)
        markup = bot.send_message.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.keyboard[-1][0].text, "Расписание")

    async def test_challenge_waits_for_onboarding(self):
        context = types.SimpleNamespace(
            bot=types.SimpleNamespace(send_message=AsyncMock()), job_queue=None)
        pending = {"user_id": 7, "step": "subscription"}
        fake_state = types.ModuleType("app.onboarding_state")
        fake_state.load_state = lambda _user_id: pending
        fake_state.save_state = unittest.mock.Mock()
        original = fake_db.is_user_onboarding_required
        fake_db.is_user_onboarding_required = lambda _user_id: True
        with patch.object(start_flow, "start_user_challenge_setup") as activate, \
                patch.dict(sys.modules, {"data.db": fake_db, "app.onboarding_state": fake_state}):
            ok, reason = await start_flow.send_challenge_welcome_dm(
                context, user_id=7, chat_id=70, practice_id=88)
        fake_db.is_user_onboarding_required = original
        self.assertTrue(ok)
        self.assertIn("онбординг", reason)
        self.assertEqual(pending["pending_challenge_practice_id"], 88)
        activate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
