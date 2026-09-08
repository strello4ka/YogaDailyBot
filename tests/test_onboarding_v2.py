import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


fake_state = types.ModuleType("app.onboarding_state")
fake_state.load_state = Mock()
fake_state.save_state = Mock()
fake_state.pending_states = Mock(return_value=[])
fake_rich = types.ModuleType("app.rich_messages")
fake_rich.paragraph = lambda text: {"type": "paragraph", "text": text}
fake_rich.button_row = lambda buttons: {"type": "buttons", "buttons": buttons}
fake_rich.send_rich_message = AsyncMock()
fake_rich.edit_rich_message = AsyncMock()

with patch.dict(sys.modules, {
    "app.onboarding_state": fake_state,
    "app.rich_messages": fake_rich,
}):
    flow = importlib.import_module("app.onboarding_flow")


class OnboardingV2Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fake_state.load_state.reset_mock()
        fake_state.save_state.reset_mock()
        self.bot = types.SimpleNamespace(
            send_message=AsyncMock(return_value=types.SimpleNamespace(message_id=99)),
            edit_message_reply_markup=AsyncMock(),
        )
        self.context = types.SimpleNamespace(bot=self.bot, bot_data={}, args=[])
        self.message = types.SimpleNamespace(text="", reply_text=AsyncMock())
        self.query = types.SimpleNamespace(
            data="", answer=AsyncMock(), message=self.message,
        )
        self.update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=7, first_name="Катя", username="katya"),
            effective_chat=types.SimpleNamespace(id=70, type="private"),
            effective_message=self.message,
            callback_query=self.query,
        )

    def state(self, step, **extra):
        return dict(user_id=7, chat_id=70, step=step, entered_at=1,
                    reminded=[], message_ids=[], **extra)

    def test_keyboards_match_flow(self):
        welcome = flow.keyboard("welcome").inline_keyboard
        self.assertEqual([row[0].text for row in welcome], ["Посмотреть пример", "Настроить бот"])
        offer = flow.keyboard("offer").inline_keyboard
        self.assertEqual([row[0].text for row in offer], ["Пропустить", "Настроить расписание"])

    def test_agreement_has_styles_and_placeholder_link(self):
        buttons = [block for block in flow.agreement_blocks() if block["type"] == "buttons"]
        self.assertEqual(buttons[0]["buttons"][0]["style"], "link")
        self.assertEqual(buttons[0]["buttons"][1]["style"], "primary")
        self.assertEqual(buttons[1]["buttons"][0]["url"], "https://example.com/")

    async def test_skip_finishes_without_schedule(self):
        state = self.state("offer", agreement_version=flow.texts.AGREEMENT_VERSION)
        fake_state.load_state.return_value = state
        self.query.data = "ob2:offer:finish"
        with patch.object(flow, "transition", new_callable=AsyncMock) as transition:
            await flow.callback(self.update, self.context)
        transition.assert_awaited_once_with(self.context, state, "complete")

    async def test_valid_time_saves_schedule_then_confirmation(self):
        state = self.state("time", agreement_version=flow.texts.AGREEMENT_VERSION)
        fake_state.load_state.return_value = state
        self.message.text = "7.00"
        fake_daily = types.ModuleType("app.daily.set_time")
        fake_daily.validate_time_format = lambda value: (True, "07:00")
        with patch.dict(sys.modules, {"app.daily.set_time": fake_daily}), \
                patch.object(flow, "transition", new_callable=AsyncMock) as transition:
            handled = await flow.handle_time_input(self.update, self.context)
        self.assertTrue(handled)
        transition.assert_awaited_once_with(
            self.context, state, "confirmation", schedule_time="07:00")

    async def test_stale_callback_does_not_move_flow(self):
        fake_state.load_state.return_value = self.state("subscription")
        self.query.data = "ob2:welcome:agreement"
        with patch.object(flow, "transition", new_callable=AsyncMock) as transition:
            await flow.callback(self.update, self.context)
        transition.assert_not_awaited()

    async def test_existing_completed_user_gets_common_keyboard(self):
        fake_state.load_state.return_value = None
        fake_db = types.ModuleType("data.db")
        fake_db.user_exists = lambda _user_id: True
        fake_db.is_user_onboarding_required = lambda _user_id: False
        with patch.dict(sys.modules, {"data.db": fake_db}):
            await flow.start_command(self.update, self.context)
        self.message.reply_text.assert_awaited_once()
        markup = self.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertEqual(markup.keyboard[-1][0].text, "Расписание")


if __name__ == "__main__":
    unittest.main()
