import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


fake_db = types.ModuleType("data.db")
fake_db.get_better_than_completed_percent = lambda *_args, **_kwargs: None
fake_db.get_challenge_completed_in_last_n_days = lambda *_args, **_kwargs: 0
fake_db.get_completed_count = lambda *_args, **_kwargs: 1
fake_db.get_streak_days = lambda *_args, **_kwargs: 0
fake_db.get_user_bot_mode = lambda *_args, **_kwargs: "daily"
fake_db.has_best_streak = lambda *_args, **_kwargs: False
fake_db.reset_user_progress = lambda *_args, **_kwargs: True
sys.modules["data.db"] = fake_db

from app.handlers import progress


class ProgressResetTest(unittest.IsolatedAsyncioTestCase):
    async def test_challenge_progress_shows_reset_button(self):
        message = types.SimpleNamespace(reply_text=AsyncMock())
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            effective_message=message,
            effective_chat=types.SimpleNamespace(id=456),
        )
        context = types.SimpleNamespace(bot=object())

        with (
            patch.object(progress, "get_completed_count", return_value=4),
            patch.object(progress, "get_streak_days", return_value=1),
            patch.object(progress, "get_challenge_completed_in_last_n_days", return_value=2),
            patch.object(progress, "get_user_bot_mode", return_value="challenge"),
            patch.object(progress, "_progress_text", return_value="Прогресс"),
            patch.object(progress, "format_social_proof_line", return_value=""),
            patch.object(progress, "send_rich_message", new=AsyncMock()) as send_rich,
        ):
            await progress.handle_progress_callback(update, context)

        blocks = send_rich.await_args.args[2]
        self.assertTrue(any("Сбросить прогресс" in str(block) for block in blocks))
        self.assertFalse(any("disabled" in str(block) for block in blocks))

    async def test_challenge_reset_requires_explicit_confirmation(self):
        query = types.SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            callback_query=query,
        )

        with patch.object(progress, "get_user_bot_mode", return_value="challenge"):
            await progress.handle_progress_reset_callback(update, None)

        text = query.edit_message_text.await_args.args[0]
        markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertIn("результат текущего челленджа", text)
        self.assertIn("нельзя отменить", text)
        self.assertEqual(markup.inline_keyboard[0][0].text, "Да, сбросить всё")

    async def test_confirmed_challenge_reset_is_executed(self):
        query = types.SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=123),
            callback_query=query,
        )

        with patch.object(progress, "reset_user_progress", return_value=True) as reset:
            await progress.handle_progress_reset_yes_callback(update, None)

        reset.assert_called_once_with(123)
        query.answer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
