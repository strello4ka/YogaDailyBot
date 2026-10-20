"""Regression tests for admin debug access and disabled schedule restoration."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from app.handlers.schedule import schedule_command, schedule_toggle_callback
from data.postgres_db import resume_disabled_daily_schedule


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

    async def test_disabled_schedule_displays_resume_even_when_not_paused(self):
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=self.settings()):
            await schedule_command(update, SimpleNamespace())
        call = update.effective_message.reply_text.await_args
        self.assertIn('приостановлена', call.args[0])
        self.assertEqual(call.kwargs['reply_markup'].inline_keyboard[0][0].text, 'Возобновить рассылку')

    async def test_resume_disabled_enables_schedule_without_pause_toggle(self):
        before = self.settings()
        after = dict(before, enabled=True)
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', side_effect=[before,after]), patch(
                'app.handlers.schedule.resume_disabled_daily_schedule', return_value=True) as resume, patch(
                'app.handlers.schedule.toggle_user_pause') as toggle:
            await schedule_toggle_callback(update, SimpleNamespace())
        resume.assert_called_once_with(10)
        toggle.assert_not_called()
        self.assertIn('с завтрашнего дня', update.callback_query.message.reply_text.await_args.args[0])
        call = update.callback_query.edit_message_text.await_args
        self.assertIn('Рассылка активна', call.kwargs['text'])
        self.assertEqual(call.kwargs['reply_markup'].inline_keyboard[0][0].text, 'Остановить рассылку')

    async def test_failed_resume_does_not_claim_success(self):
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=self.settings()), patch(
                'app.handlers.schedule.resume_disabled_daily_schedule', return_value=False):
            await schedule_toggle_callback(update, SimpleNamespace())
        self.assertIn('Не получилось', update.callback_query.message.reply_text.await_args.args[0])

    async def test_challenge_is_not_reenabled_as_daily(self):
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=self.settings(
                bot_mode='challenge', challenge_start_id=1)), patch(
                'app.handlers.schedule.resume_disabled_daily_schedule') as resume, patch(
                'app.handlers.schedule.toggle_user_pause') as toggle:
            await schedule_toggle_callback(update, SimpleNamespace())
        resume.assert_not_called()
        toggle.assert_not_called()

    async def test_missing_time_requests_setup_instead_of_enabling(self):
        update = self.update()
        with patch('app.handlers.schedule.get_user_schedule_settings', return_value=self.settings(
                notify_time='00:00')), patch('app.handlers.schedule.resume_disabled_daily_schedule') as resume, patch(
                'app.handlers.schedule.send_schedule_time_prompt', new_callable=AsyncMock) as prompt:
            await schedule_toggle_callback(update, SimpleNamespace())
        resume.assert_not_called()
        prompt.assert_awaited_once()

    def test_resume_sql_preserves_time_progress_and_excludes_challenge(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.rowcount = 1
        with patch('data.postgres_db.get_connection', return_value=connection):
            self.assertTrue(resume_disabled_daily_schedule(10))
        sql, params = cursor.execute.call_args.args
        for fragment in ('daily_schedule_enabled=TRUE', 'is_paused=FALSE',
                         'first_daily_send_date=%s', "bot_mode IS DISTINCT FROM 'challenge'"):
            self.assertIn(fragment, sql)
        self.assertNotIn('total_practices=', sql)
        self.assertNotIn('program_position=', sql)
        self.assertNotIn('notify_time=', sql)
        self.assertEqual(params[-1], 10)
        connection.close.assert_called_once()
