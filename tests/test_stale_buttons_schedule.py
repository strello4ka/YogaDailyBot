"""Проверки расписания и отсутствия обхода старых кнопок при выдаче, без БД."""
import ast
import unittest
from datetime import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


class StaleButtonsScheduleTest(unittest.TestCase):
    def test_midnight_and_morning_use_same_job_and_moscow_timezone(self):
        tree = ast.parse((ROOT / 'app/handlers/done.py').read_text())
        tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == 'schedule_strip_done_buttons_midnight']
        job = Mock()
        ns = dict(time=time, MOSCOW_TZ=ZoneInfo('Europe/Moscow'),
                  logger=Mock(), strip_stale_done_buttons_job=job)
        exec(compile(tree, '<schedule>', 'exec'), ns)
        queue = Mock()
        ns['schedule_strip_done_buttons_midnight'](SimpleNamespace(job_queue=queue))
        calls = queue.run_daily.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual([c.kwargs['time'] for c in calls],
                         [time(0, tzinfo=ns['MOSCOW_TZ']), time(6, tzinfo=ns['MOSCOW_TZ'])])
        self.assertEqual([c.args for c in calls], [(job,), (job,)])
        self.assertEqual(len({c.kwargs['name'] for c in calls}), 2)
        queue.run_repeating.assert_not_called()

    def test_delivery_paths_do_not_call_old_button_cleanup(self):
        for path in ('app/by_mood/send_utils.py', 'app/schedule/scheduler.py'):
            with self.subTest(path=path):
                tree = ast.parse((ROOT / path).read_text())
                calls = [n.func.id for n in ast.walk(tree)
                         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
                self.assertNotIn('strip_previous_day_done_button', calls)
                self.assertIn('log_practice_sent', calls)
                self.assertIn('schedule_done_reminders', calls)
