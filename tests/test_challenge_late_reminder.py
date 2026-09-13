"""Изолированные проверки без импорта data.db (он подключается к БД)."""
import ast
import unittest
from datetime import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo


class LateReminderTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).parents[1] / 'app/handlers/done.py').read_text())
        names = {'send_challenge_late_reminders_job', 'schedule_done_evening_reminders'}
        tree.body = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
        self.ns = dict(
            ContextTypes=SimpleNamespace(DEFAULT_TYPE=object),
            get_users_for_challenge_late_reminder=Mock(return_value=[(1, 11)]),
            has_completed_practice_today=Mock(return_value=False),
            pick_done_reminder_text=Mock(return_value='Практика все еще ждет тебя 🧡'),
            mark_blocked_if_forbidden=Mock(return_value=False),
            logger=Mock(), time=time, MOSCOW_TZ=ZoneInfo('Europe/Moscow'),
            send_evening_done_reminders_failsafe_job=Mock(),
        )
        exec(compile(tree, '<reminders>', 'exec'), self.ns)
        self.context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))

    async def run_job(self, day):
        cohort = SimpleNamespace(CHALLENGE_DURATION=28, is_cohort_configured=lambda: True, get_cohort_challenge_day=lambda: day)
        with patch.dict('sys.modules', {'app.challenge.cohort': cohort}):
            await self.ns['send_challenge_late_reminders_job'](self.context)

    async def test_active_last_day_gets_fixed_text(self):
        await self.run_job(28)
        self.context.bot.send_message.assert_awaited_once_with(chat_id=11, text='Я знаю, чем ты занимаешься перед сном, маленький йог..не забудь нажать кнопку "Я сделал!"', parse_mode='Markdown')

    async def test_before_start_and_after_finish_no_recipients_loaded(self):
        for day in (0, 29, 40):
            await self.run_job(day)
        self.ns['get_users_for_challenge_late_reminder'].assert_not_called()
        self.context.bot.send_message.assert_not_awaited()

    async def test_done_no_message(self):
        self.ns['has_completed_practice_today'].return_value = True
        await self.run_job(5)
        self.context.bot.send_message.assert_not_awaited()

    async def test_no_eligible_participants_no_message(self):
        self.ns['get_users_for_challenge_late_reminder'].return_value = []
        await self.run_job(5)
        self.context.bot.send_message.assert_not_awaited()

    def test_schedule_moscow_2350_and_existing_failsafe(self):
        queue = Mock()
        self.ns['schedule_done_evening_reminders'](SimpleNamespace(job_queue=queue))
        self.assertEqual(queue.run_daily.call_args.kwargs['time'], time(23, 50, tzinfo=ZoneInfo('Europe/Moscow')))
        queue.run_repeating.assert_called_once()
