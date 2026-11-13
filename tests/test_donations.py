"""The former donations entry is now subscription-only."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.ext import ApplicationHandlerStop

from app.handlers.donations import handle_donations_callback, handle_legacy_donation_callback
from app.subscription.subscription_menu import guard_update


class DonationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_donations_open_only_configured_miniapp(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(bot=bot,
                                  bot_data={"subscription_miniapp_url": "https://payments.example.test/"},
                                  user_data={})
        update = SimpleNamespace(callback_query=None, effective_chat=SimpleNamespace(id=123))

        await handle_donations_callback(update, context)

        sent = bot.send_message.call_args.kwargs
        self.assertIn("нет активных подписок", sent["text"])
        buttons = [row[0] for row in sent["reply_markup"].inline_keyboard]
        self.assertEqual([button.text for button in buttons], ["Посмотреть тарифы"])
        self.assertEqual(buttons[0].web_app.url, "https://payments.example.test/")

    async def test_donations_do_not_offer_tariffs_without_configured_miniapp(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(bot=bot, bot_data={}, user_data={})
        update = SimpleNamespace(callback_query=None, effective_chat=SimpleNamespace(id=123))

        await handle_donations_callback(update, context)

        sent = bot.send_message.call_args.kwargs
        self.assertIn("Не удалось загрузить данные о подписке", sent["text"])
        self.assertNotIn("reply_markup", sent)

    async def test_old_donation_buttons_cannot_restart_removed_flow(self):
        query = SimpleNamespace(answer=AsyncMock())

        await handle_legacy_donation_callback(
            SimpleNamespace(callback_query=query), SimpleNamespace()
        )

        self.assertTrue(query.answer.await_args.kwargs["show_alert"])

    @patch("app.onboarding.state.load_state", return_value={"step": "complete"})
    @patch("app.subscription.access.repository_for")
    async def test_new_account_without_subscription_row_gets_free_menu(self, repository_for, _state):
        repository = SimpleNamespace(synchronize_access=lambda _user_id, _now: None)
        repository_for.return_value = repository
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(
            bot=bot,
            bot_data={"subscription_miniapp_url": "https://payments.example.test/"},
            user_data={},
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=42),
            effective_chat=SimpleNamespace(id=123, type="private"),
            effective_message=SimpleNamespace(text="/donate"),
            callback_query=None,
        )

        with self.assertRaises(ApplicationHandlerStop):
            await guard_update(update, context)

        self.assertIn("нет активных подписок", bot.send_message.await_args.kwargs["text"])


if __name__ == "__main__":
    unittest.main()
