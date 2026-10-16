"""LISTEN/NOTIFY is a wakeup, never an authorization or a durable payment queue."""
import asyncio
import logging
from contextlib import suppress
from types import SimpleNamespace

from .jobs import reconcile_test_payments, _send_restore_offer
from .tariff import MOSCOW
from datetime import datetime

logger = logging.getLogger(__name__)
CHANNEL = 'subscription_payment_ready'


def _connect(factory):
    connection = factory()
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database()')
            if cursor.fetchone()[0] != 'yogadaily_test':
                raise ValueError('Payment listener requires the isolated test database')
            cursor.execute('LISTEN ' + CHANNEL)
        return connection
    except BaseException:
        connection.close()
        raise


async def process_wakeup(context, payload):
    if not isinstance(payload, str) or not payload.isdigit():
        return
    user_id = int(payload)
    if user_id <= 0:
        return
    allowed = context.bot_data.get('subscription_test_users')
    if allowed is not None and user_id not in allowed:
        return
    # The shared worker re-reads verified durable orders and uses the existing
    # PostgreSQL notification locks. Payload alone cannot grant or notify access.
    await reconcile_test_payments(context, user_ids={user_id})
    await _send_restore_offer(context, user_id, datetime.now(MOSCOW))


async def listen(application, factory):
    context = SimpleNamespace(bot=application.bot, bot_data=application.bot_data)
    loop = asyncio.get_running_loop()
    while True:
        connection, fd = None, None
        try:
            connection = await asyncio.to_thread(_connect, factory)
            ready = asyncio.Event()
            fd = connection.fileno()
            loop.add_reader(fd, ready.set)
            logger.info('Test payment wakeup listener started')
            while True:
                await ready.wait()
                ready.clear()
                connection.poll()
                payloads = {notice.payload for notice in connection.notifies}
                connection.notifies.clear()
                for payload in payloads:
                    try:
                        await process_wakeup(context, payload)
                    except Exception:
                        logger.warning('Test payment wakeup processing failed; periodic delivery remains active')
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning('Test payment listener disconnected; retrying, periodic delivery remains active')
        finally:
            if fd is not None:
                loop.remove_reader(fd)
            if connection is not None:
                connection.close()
        await asyncio.sleep(5)


def install(application, factory):
    previous_init, previous_stop = application.post_init, application.post_stop

    async def start(app):
        if previous_init:
            await previous_init(app)
        app.bot_data['subscription_payment_listener_task'] = asyncio.create_task(listen(app, factory))

    async def stop(app):
        task = app.bot_data.pop('subscription_payment_listener_task', None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if previous_stop:
            await previous_stop(app)

    application.post_init, application.post_stop = start, stop
