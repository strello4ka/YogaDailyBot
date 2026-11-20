import asyncio
import unittest
from types import SimpleNamespace

from telegram.error import BadRequest

from app.handlers.breathing import breathing_command


class FakeBot:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def _post(self, method, payload):
        self.calls.append((method, payload))
        if self.error:
            raise self.error


class BreathingWidgetTests(unittest.TestCase):
    def test_sends_square_mvp_widget(self):
        bot = FakeBot()
        message = SimpleNamespace(is_topic_message=False, message_thread_id=None)
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=42, type="private"),
            effective_message=message,
        )

        asyncio.run(breathing_command(update, SimpleNamespace(bot=bot)))

        method, payload = bot.calls[0]
        self.assertEqual(method, "sendWidget")
        self.assertEqual(payload["chat_id"], 42)
        self.assertIn("aspect-ratio:1", payload["html"])
        self.assertIn('data-min="5"', payload["html"])
        self.assertIn('data-pattern="46"', payload["html"])
        self.assertLessEqual(len(payload["html"].encode()), 32 * 1024)

    def test_falls_back_when_widget_is_unavailable(self):
        replies = []

        async def reply_text(text):
            replies.append(text)

        message = SimpleNamespace(
            is_topic_message=False,
            message_thread_id=None,
            reply_text=reply_text,
        )
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(id=42, type="private"),
            effective_message=message,
        )

        asyncio.run(
            breathing_command(
                update,
                SimpleNamespace(bot=FakeBot(BadRequest("unsupported"))),
            )
        )

        self.assertEqual(len(replies), 1)
        self.assertIn("не поддерживается", replies[0])


if __name__ == "__main__":
    unittest.main()
