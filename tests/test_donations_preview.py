"""Production donations entry stays on the payment-disabled Mini App preview."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.handlers.donations import (
    MINIAPP_PREVIEW_URL,
    handle_donate_card_callback,
    handle_donations_callback,
)


class DonationsPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_donations_keep_stars_and_open_preview_without_card_button(self):
        bot = SimpleNamespace(send_message=AsyncMock())
        context = SimpleNamespace(bot=bot,
                                  bot_data={"subscription_miniapp_url": "https://payments.example.test/"},
                                  user_data={})
        update = SimpleNamespace(callback_query=None, effective_chat=SimpleNamespace(id=123))

        await handle_donations_callback(update, context)

        sent = bot.send_message.call_args.kwargs
        self.assertIn("Пока YogaDailyBot бесплатный", sent["text"])
        buttons = [row[0] for row in sent["reply_markup"].inline_keyboard]
        self.assertEqual(buttons[0].callback_data, "donate_stars")
        self.assertEqual(buttons[1].text, "Посмотреть тарифы")
        self.assertEqual(buttons[1].web_app.url, MINIAPP_PREVIEW_URL)
        self.assertNotIn("donate_card", [button.callback_data for button in buttons])

    async def test_old_card_button_no_longer_shares_payment_details(self):
        query = SimpleNamespace(answer=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())

        await handle_donate_card_callback(SimpleNamespace(callback_query=query),
                                          SimpleNamespace(bot=bot))

        query.answer.assert_awaited_once()
        bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
