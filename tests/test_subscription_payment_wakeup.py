"""Fast notifications reuse durable payment processing and stop cleanly."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from app.subscription.payment_wakeup import _connect, install, listen, process_wakeup


class PaymentWakeupTest(unittest.IsolatedAsyncioTestCase):
    async def test_only_allowed_user_is_dispatched_before_schedule_offer(self):
        context = SimpleNamespace(bot_data={'subscription_test_users': {10}})
        calls = []
        async def reconcile(*args, **kwargs):
            calls.append('payment')
            self.assertEqual(kwargs['user_ids'], {10})
        async def restore(*args):
            calls.append('schedule')
        with patch('app.subscription.payment_wakeup.reconcile_test_payments', side_effect=reconcile), patch(
                'app.subscription.payment_wakeup._send_restore_offer', side_effect=restore):
            for payload in ('bad', '0', '-1', '11'):
                await process_wakeup(context, payload)
            self.assertEqual(calls, [])
            await process_wakeup(context, '10')
            self.assertEqual(calls, ['payment', 'schedule'])

    async def test_listener_reads_notifications_and_cleans_up_on_stop(self):
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        connection = MagicMock()
        connection.fileno.return_value = read_fd
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ('yogadaily_test',)
        connection.notifies = []
        def poll():
            try:
                os.read(read_fd, 100)
            except BlockingIOError:
                return
            connection.notifies.append(SimpleNamespace(payload='10'))
        connection.poll.side_effect = poll
        seen = asyncio.Event()
        async def process(context, payload):
            self.assertEqual(payload, '10')
            seen.set()
        app = SimpleNamespace(bot=Mock(), bot_data={})
        task = None
        try:
            with patch('app.subscription.payment_wakeup.process_wakeup', side_effect=process):
                task = asyncio.create_task(listen(app, lambda: connection))
                os.write(write_fd, b'wakeup')
                await asyncio.wait_for(seen.wait(), 2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            connection.close.assert_called_once()
        finally:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            os.close(read_fd)
            os.close(write_fd)

    async def test_lifecycle_keeps_existing_hooks_and_cancels_listener(self):
        init, stop = AsyncMock(), AsyncMock()
        app = SimpleNamespace(post_init=init, post_stop=stop, bot_data={})
        ready = asyncio.Event()
        async def idle(*args):
            ready.set()
            await asyncio.Event().wait()
        with patch('app.subscription.payment_wakeup.listen', side_effect=idle):
            install(app, Mock())
            await app.post_init(app)
            await asyncio.wait_for(ready.wait(), 1)
            await app.post_stop(app)
        init.assert_awaited_once_with(app)
        stop.assert_awaited_once_with(app)
        self.assertNotIn('subscription_payment_listener_task', app.bot_data)

    def test_listener_rejects_wrong_database_and_closes_connection(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ('production',)
        with self.assertRaises(ValueError):
            _connect(lambda: connection)
        connection.close.assert_called_once()
        self.assertNotIn('LISTEN', str(cursor.execute.call_args_list))
