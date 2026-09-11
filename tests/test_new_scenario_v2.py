import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import onboarding_messages as messages
from app.keyboards import get_common_reply_keyboard
from app.challenge.flow.start_flow import build_challenge_welcome_text
from app.handlers.progress import _progress_blocks
from app.challenge.flow.post_challenge import keyboard as post_challenge_keyboard
from app.onboarding_flow import handle_reply


class NewScenarioCopyTest(unittest.TestCase):
    def test_permanent_keyboard_has_final_layout_and_labels(self):
        rows = [[button.text for button in row] for row in get_common_reply_keyboard().keyboard]
        self.assertEqual(rows, [
            ["ленивые дни", "без коврика"],
            ["здоровая спина", "расслабление"],
            ["мини", "strello4ka"],
            ["хард", "практика дня"],
            ["САМ решу"],
            ["расписание"],
        ])

    def test_expandable_copy_is_used_on_specified_screens(self):
        self.assertIn("<blockquote expandable>", messages.welcome("Катя"))
        self.assertIn("<blockquote expandable>", messages.SCHEDULE_OFFER)
        self.assertIn("<blockquote expandable>", messages.WEEK)
        self.assertIn("<blockquote expandable>", messages.COMPLETE)

    @patch("app.challenge.flow.start_flow.get_challenge_start_date")
    def test_challenge_welcome_contains_date_range_and_week_quote(self, get_start):
        from datetime import date
        get_start.return_value = date(2026, 9, 14)
        text = build_challenge_welcome_text()
        self.assertIn("14.09", text)
        self.assertIn("11.10", text)
        self.assertIn("<blockquote expandable>", text)

    @patch("app.handlers.progress.get_user_bot_mode", return_value="by_mood")
    def test_progress_stats_are_paragraphs_not_disabled_buttons(self, _mode):
        blocks = _progress_blocks(1, 4, 1, "")
        self.assertTrue(all(block.get("type") != "buttons" for block in blocks[:-1]))
        self.assertFalse(any("disabled" in str(block) for block in blocks))

    def test_post_challenge_actions_keep_expected_layout(self):
        rows = [[button.text for button in row] for row in post_challenge_keyboard("07:00").inline_keyboard]
        self.assertEqual(rows, [["Не хочу", "Изменить время"], ["Продолжить в 07:00"]])

    @patch("app.onboarding_flow.load_state", return_value={"step": "declined"})
    def test_declined_user_cannot_bypass_agreement_with_text(self, _state):
        message = SimpleNamespace(text="09.30", reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_message=message)
        handled = __import__("asyncio").run(handle_reply(update, SimpleNamespace()))
        self.assertTrue(handled)
        message.reply_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
