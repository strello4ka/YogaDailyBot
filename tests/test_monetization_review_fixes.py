"""Regression tests for admin debug access and disabled schedule restoration."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from app.handlers.schedule import FIRST_SETUP_TEXT, schedule_command, schedule_toggle_callback
from data.postgres_db import disable_daily_schedule


class DebugPracticeAccessTest(unittest.IsolatedAsyncioTestCase):
    async def test_only_owner_can_request_debug_practice(self):
        # Load the actual handler without importing the application's startup.
        source = Path(__file__).resolve().parents[1] / 'app/main.py'
        tree = ast.parse(source.read_text())
        handler = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                       and n.name == 'test_practice_command')
        send = AsyncMock()
        scope = dict(ADMIN_USER_ID=946774551, Update=object, logger=Mock(), send_test_practice=send)
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), 'exec'), scope)
        context = SimpleNamespace()
        for user_id in (424904828, 946774551):
            reply = AsyncMock()
            update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id),
                                     effective_chat=SimpleNamespace(id=user_id),
                                     message=SimpleNamespace(reply_text=reply))
            await scope['test_practice_command'](update, context)
            if user_id != 946774551:
                send.assert_not_awaited()
                self.assertIn('только владельцу', reply.await_args.args[0])
        send.assert_awaited_once_with(context, 946774551, 946774551)


class DisabledScheduleTest(unittest.IsolatedAsyncioTestCase):
    def settings(self, **changes):
        values = dict(notify_time='09:00', enabled=False, paused=False,
                      bot_mode='daily', challenge_start_id=None)
        values.update(changes)
        return values

    def update(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock(), message=message)
        return SimpleNamespace(effective_user=SimpleNamespace(id=10),
            effective_message=message, effective_chat=SimpleNamespace(id=10), callback_query=query)

    async def test_disabled_schedule_uses_the_unconfigured_flow(self):
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=self.settings()):
            await schedule_command(update, SimpleNamespace(user_data={}))
        call = update.effective_message.reply_text.await_args
        self.assertEqual(call.args[0], FIRST_SETUP_TEXT)
        self.assertEqual(call.kwargs['reply_markup'].inline_keyboard[0][0].text, 'Выбрать время')

    async def test_stop_removes_schedule_and_offers_setup_again(self):
        before = self.settings(enabled=True)
        update = self.update()
        update.callback_query.edit_message_reply_markup = AsyncMock()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=before), patch(
                'app.handlers.schedule.disable_daily_schedule', return_value=True) as disable:
            await schedule_toggle_callback(update, SimpleNamespace())
        disable.assert_called_once_with(10)
        update.callback_query.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)
        call = update.callback_query.message.reply_text.await_args
        self.assertIn('Остановил ежедневную рассылку', call.args[0])
        button = call.kwargs['reply_markup'].inline_keyboard[0][0]
        self.assertEqual(button.text, 'Возобновить рассылку')
        self.assertEqual(button.callback_data, 'schedule_resume_setup')

    async def test_failed_stop_does_not_claim_success(self):
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=self.settings(enabled=True)), patch(
                'app.handlers.schedule.disable_daily_schedule', return_value=False):
            await schedule_toggle_callback(update, SimpleNamespace())
        self.assertIn('Не получилось', update.callback_query.message.reply_text.await_args.args[0])

    async def test_challenge_is_not_reenabled_as_daily(self):
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=self.settings(
                bot_mode='challenge', challenge_start_id=1)), patch(
                'app.handlers.schedule.disable_daily_schedule') as disable:
            await schedule_toggle_callback(update, SimpleNamespace())
        disable.assert_not_called()

    async def test_legacy_paused_schedule_uses_unconfigured_flow(self):
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=self.settings(
                enabled=True, paused=True)):
            await schedule_command(update, SimpleNamespace(user_data={}))
        self.assertEqual(update.effective_message.reply_text.await_args.args[0], FIRST_SETUP_TEXT)

    def test_disable_sql_clears_schedule_and_preserves_progress(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        with patch('data.postgres_db.get_connection', return_value=connection):
            self.assertTrue(disable_daily_schedule(10))
        sql, params = cursor.execute.call_args.args
        for fragment in ("notify_time='00:00'", 'daily_schedule_enabled=FALSE',
                         'is_paused=FALSE', "bot_mode IS DISTINCT FROM 'challenge'"):
            self.assertIn(fragment, sql)
        self.assertNotIn('total_practices=', sql)
        self.assertNotIn('program_position=', sql)
        self.assertEqual(params, (10,))
        connection.close.assert_called_once()
