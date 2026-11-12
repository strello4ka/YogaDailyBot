"""Donations entry uses only the configured subscription Mini App."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.donations import handle_donate_card_callback, handle_donations_callback


class DonationsTests(unittest.IsolatedAsyncioTestCase):
    async def test_donations_open_only_configured_miniapp(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(bot=bot,
                                  bot_data={"subscription_miniapp_url": "https://payments.example.test/"},
                                  user_data={})
        update = SimpleNamespace(callback_query=None, effective_chat=SimpleNamespace(id=123))

        await handle_donations_callback(update, context)

        sent = bot.send_message.call_args.kwargs
        self.assertIn("Поддержка YogaDailyBot", sent["text"])
        buttons = [row[0] for row in sent["reply_markup"].inline_keyboard]
        self.assertEqual(buttons[0].callback_data, "donate_stars")
        self.assertNotIn("⭐", buttons[0].text)
        self.assertEqual(buttons[1].text, "Посмотреть тарифы")
        self.assertEqual(buttons[1].web_app.url, "https://payments.example.test/")
        self.assertNotIn("donate_card", [button.callback_data for button in buttons])

    async def test_donations_do_not_offer_tariffs_without_configured_miniapp(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(bot=bot, bot_data={}, user_data={})
        update = SimpleNamespace(callback_query=None, effective_chat=SimpleNamespace(id=123))

        await handle_donations_callback(update, context)

        buttons = [row[0] for row in bot.send_message.call_args.kwargs["reply_markup"].inline_keyboard]
        self.assertEqual([button.callback_data for button in buttons], ["donate_stars"])

    async def test_old_card_button_no_longer_shares_payment_details(self):
        query = SimpleNamespace(answer=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())

        await handle_donate_card_callback(SimpleNamespace(callback_query=query),
                                          SimpleNamespace(bot=bot))

        query.answer.assert_awaited_once()
        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
