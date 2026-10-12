import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from telegram.constants import ChatType


def _load_block_module():
    fake_db = types.ModuleType("data.db")
    fake_db.clear_user_blocked_if_needed = Mock(return_value=False)
    fake_db.set_user_blocked = Mock(return_value=True)

    path = Path(__file__).resolve().parents[1] / "app" / "block.py"
    spec = importlib.util.spec_from_file_location("block_activity_under_test", path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get("data.db")
    sys.modules["data.db"] = fake_db
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop("data.db", None)
        else:
            sys.modules["data.db"] = previous
    return module, fake_db


class BlockActivityTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _member_update(status):
        return SimpleNamespace(
            my_chat_member=SimpleNamespace(
                chat=SimpleNamespace(type=ChatType.PRIVATE, id=123),
                new_chat_member=SimpleNamespace(
                    status=status,
                    user=SimpleNamespace(is_bot=True),
                ),
            )
        )

    async def test_private_message_clears_stale_block(self):
        module, fake_db = _load_block_module()
        fake_db.clear_user_blocked_if_needed.return_value = True
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(type=ChatType.PRIVATE),
            effective_user=SimpleNamespace(id=123, is_bot=False),
            message=SimpleNamespace(text="Привет"),
            callback_query=None,
        )

        await module.clear_stale_block_on_private_activity(update, None)

        fake_db.clear_user_blocked_if_needed.assert_called_once_with(123)

    async def test_start_is_left_for_start_command(self):
        module, fake_db = _load_block_module()
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(type=ChatType.PRIVATE),
            effective_user=SimpleNamespace(id=123, is_bot=False),
            message=SimpleNamespace(text="/start"),
            callback_query=None,
        )

        await module.clear_stale_block_on_private_activity(update, None)

        fake_db.clear_user_blocked_if_needed.assert_not_called()

    async def test_private_callback_clears_stale_block(self):
        module, fake_db = _load_block_module()
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(type=ChatType.PRIVATE),
            effective_user=SimpleNamespace(id=456, is_bot=False),
            message=None,
            callback_query=SimpleNamespace(data="button"),
        )

        await module.clear_stale_block_on_private_activity(update, None)

        fake_db.clear_user_blocked_if_needed.assert_called_once_with(456)

    async def test_group_message_does_not_change_block_flag(self):
        module, fake_db = _load_block_module()
        update = SimpleNamespace(
            effective_chat=SimpleNamespace(type=ChatType.GROUP),
            effective_user=SimpleNamespace(id=789, is_bot=False),
            message=SimpleNamespace(text="hello"),
            callback_query=None,
        )

        await module.clear_stale_block_on_private_activity(update, None)

        fake_db.clear_user_blocked_if_needed.assert_not_called()

    async def test_telegram_banned_event_sets_block_flag(self):
        module, fake_db = _load_block_module()

        await module.handle_user_block_event(
            self._member_update(module.ChatMemberStatus.BANNED),
            SimpleNamespace(user_data={"just_unblocked": True}),
        )

        fake_db.set_user_blocked.assert_called_once_with(123, True)

    async def test_telegram_member_event_clears_block_flag(self):
        module, fake_db = _load_block_module()

        context = SimpleNamespace(user_data={})
        await module.handle_user_block_event(
            self._member_update(module.ChatMemberStatus.MEMBER),
            context,
        )

        fake_db.set_user_blocked.assert_called_once_with(123, False)
        self.assertTrue(context.user_data["just_unblocked"])


if __name__ == "__main__":
    unittest.main()
