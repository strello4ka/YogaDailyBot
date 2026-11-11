import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.constants import ChatType

from app.activity import record_private_user_activity


class UserActivityTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def update(*, message=None, callback_query=None, chat_type=ChatType.PRIVATE,
               is_bot=False):
        return SimpleNamespace(
            effective_chat=SimpleNamespace(type=chat_type),
            effective_user=SimpleNamespace(id=123, is_bot=is_bot),
            message=message,
            callback_query=callback_query,
        )

    @patch("app.activity.asyncio.to_thread", new_callable=AsyncMock)
    async def test_private_message_resets_inactivity(self, to_thread):
        await record_private_user_activity(
            self.update(message=SimpleNamespace(text="/donate")), None
        )

        function, user_id = to_thread.await_args.args
        self.assertEqual(function.__name__, "touch_user_activity_for_inactivity_reminders")
        self.assertEqual(user_id, 123)

    @patch("app.activity.asyncio.to_thread", new_callable=AsyncMock)
    async def test_private_callback_resets_inactivity(self, to_thread):
        await record_private_user_activity(
            self.update(callback_query=SimpleNamespace(data="pc:continue")), None
        )

        to_thread.assert_awaited_once()

    @patch("app.activity.asyncio.to_thread", new_callable=AsyncMock)
    async def test_group_message_does_not_reset_private_inactivity(self, to_thread):
        await record_private_user_activity(
            self.update(message=SimpleNamespace(text="hello"), chat_type=ChatType.GROUP),
            None,
        )

        to_thread.assert_not_awaited()

    @patch("app.activity.asyncio.to_thread", new_callable=AsyncMock)
    async def test_bot_update_is_ignored(self, to_thread):
        await record_private_user_activity(
            self.update(message=SimpleNamespace(text="hello"), is_bot=True), None
        )

        to_thread.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
