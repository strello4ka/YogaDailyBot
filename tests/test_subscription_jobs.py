import unittest
from datetime import datetime, timedelta
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
from unittest.mock import patch

from app.subscription.access import Subscription
from app.subscription.demo import start_trial
from app.subscription.old_users.rules import GiftPeriod
from app.subscription.old_users.rules import launch_offer
from dataclasses import replace
from app.subscription.jobs import due_reminders, reconcile_test_payments, deliver_payment_notice
from app.subscription.jobs import deliver_test_reminders, Reminder, _send_reminder
from app.subscription.tariff import MOSCOW, purchased_period


def at(day, hour=0):
    return datetime(2026, 10, day, hour, tzinfo=MOSCOW)


class SubscriptionRemindersTest(unittest.TestCase):
    def test_all_old_user_reminders_are_due_only_on_their_scheduled_day(self):
        from app.subscription.old_users.notifications import notification_schedule
        offer = launch_offer(at(1))
        state = Subscription(gift=offer.gift)
        for notification in notification_schedule(offer):
            with self.subTest(kind=notification.kind):
                moment = notification.scheduled_at
                before = due_reminders(state, moment - timedelta(seconds=1), old_user_offer=offer)
                self.assertNotIn(notification.kind, [item.kind for item in before])
                events = due_reminders(state, moment, old_user_offer=offer)
                matching = [item for item in events if item.kind == notification.kind]
                self.assertEqual(len(matching), 1)
                self.assertEqual(matching[0].offer_ends_at, offer.offer_ends)
                tomorrow = due_reminders(state, moment + timedelta(days=1), old_user_offer=offer)
                self.assertNotIn(notification.kind, [item.kind for item in tomorrow])

    def test_pending_checkout_suppresses_old_user_sales_but_not_access_expiry(self):
        from app.subscription.old_users.notifications import notification_schedule
        offer = launch_offer(at(1))
        for event in notification_schedule(offer):
            actual = due_reminders(Subscription(gift=offer.gift), event.scheduled_at,
                                   old_user_offer=offer, payment_pending=True)
            if event.kind == 'launch':
                expected = ['launch']
            elif event.kind == 'launch_feedback':
                expected = ['launch', 'launch_feedback']
            else:
                expected = ['gift_expired'] if event.kind == 'gift_expired' else []
            self.assertEqual([item.kind for item in actual], expected)

    def test_old_user_purchase_suppresses_sales_and_preserves_paid_activation(self):
        from app.subscription.old_users.notifications import notification_schedule
        offer = launch_offer(at(1))
        paid = purchased_period('month', at(2), trial_ends_at=offer.gift.ends_at)
        state = Subscription(gift=offer.gift, paid=paid)
        for event in notification_schedule(offer):
            actual = due_reminders(state, event.scheduled_at, old_user_offer=offer)
            if event.kind in ('launch', 'launch_feedback'):
                self.assertIn(event.kind, [item.kind for item in actual])
            else:
                self.assertNotIn(event.kind, [item.kind for item in actual])
        self.assertEqual([item.kind for item in due_reminders(
            state, offer.gift.ends_at + timedelta(hours=8), old_user_offer=offer)],
            ['gift_subscription_activated'])
        used = replace(offer, used_at=at(2))
        for event in notification_schedule(offer)[5:]:
            self.assertEqual(due_reminders(Subscription(gift=offer.gift), event.scheduled_at,
                                          old_user_offer=used), [])

    def setUp(self):
        self.trial = start_trial(at(1))
        self.state = Subscription(self.trial)

    def test_trial_notifications_times(self):
        for day, hour, expected in [(12, 13, 'trial_three_days'), (14, 19, 'trial_last_day'),
                                    (15, 8, 'trial_expired'), (22, 10, 'trial_followup')]:
            with self.subTest(expected=expected):
                self.assertEqual(due_reminders(self.state, at(day, hour) - timedelta(seconds=1)), [])
                events = due_reminders(self.state, at(day, hour))
                self.assertEqual([r.kind for r in events], [expected])
                self.assertEqual(events[0].key, due_reminders(self.state, at(day, hour + 1))[0].key)

    def test_prepaid_trial_has_no_sales_and_activates_at_eight(self):
        paid = purchased_period('month', at(2), trial_ends_at=self.trial.ends_at)
        state = Subscription(self.trial, paid)
        for moment in (at(12, 13), at(14, 19), at(22, 10)):
            self.assertEqual(due_reminders(state, moment), [])
        self.assertEqual(
            [event.kind for event in due_reminders(state, at(15, 8))],
            ['trial_subscription_activated'],
        )

    def test_prepaid_gift_activates_at_eight(self):
        gift = GiftPeriod(at(1), at(15))
        paid = purchased_period('month', at(2), trial_ends_at=gift.ends_at)
        state = Subscription(paid=paid, gift=gift)
        self.assertEqual(due_reminders(state, at(15, 8) - timedelta(seconds=1)), [])
        event = due_reminders(state, at(15, 8))[0]
        self.assertEqual(event.kind, 'gift_subscription_activated')
        self.assertEqual(event.period_ends_at, paid.ends_at)

    def test_renewal_invalidates_old_reminder(self):
        first = purchased_period('month', at(1))
        moment = first.ends_at - timedelta(days=3) + timedelta(hours=13)
        event = due_reminders(Subscription(paid=first), moment)[0]
        renewed = purchased_period('month', moment, subscription_ends=first.ends_at)
        # Repository will retain the original start for continuous coverage.
        from app.subscription.tariff import PaidPeriod
        combined = PaidPeriod(first.starts_at, renewed.ends_at)
        self.assertEqual(due_reminders(Subscription(paid=combined), moment), [])
        next_moment = combined.ends_at - timedelta(days=3) + timedelta(hours=13)
        self.assertNotEqual(event.key, due_reminders(Subscription(paid=combined), next_moment)[0].key)

    def test_no_backlog_or_repeated_weekly_followup(self):
        self.assertEqual(due_reminders(self.state, at(16, 12)), [])
        self.assertEqual(due_reminders(self.state, at(29, 10)), [])


class PaymentWorkerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        continuation = patch('app.onboarding.flow.continue_after_subscription_payment', new_callable=AsyncMock)
        continuation.start()
        self.addCleanup(continuation.stop)
        self.repo = Mock()
        self.sent = set()
        self.pending = ['order-1']
        self.granted = []
        self.canceled = []
        self.repo.payment_work.side_effect = lambda user: (list(self.pending), list(self.granted))
        self.repo.canceled_payment_work.side_effect = lambda user: list(self.canceled)
        self.repo.notification_lock.side_effect = lambda *args: nullcontext(True)
        self.repo.notification_sent.side_effect = lambda user, key: key in self.sent
        self.repo.mark_notification_sent.side_effect = lambda user, key, now: self.sent.add(key)
        self.repo.payment_notice.return_value = (10, '<Катя>', at(30))
        self.repo.canceled_payment_notice.return_value = 10
        self.service = Mock()
        def confirm(*args):
            self.pending.clear()
            self.granted[:] = ['order-1']
            return {'status': 'succeeded'}
        self.service.refresh_details.side_effect = confirm
        self.context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), bot_data={
            'subscription_repository': self.repo, 'subscription_payment_service': self.service,
            'subscription_test_users': {10}, 'subscription_miniapp_url':'https://example.org',
        })

    async def test_closed_miniapp_does_not_prevent_confirmation_and_notice(self):
        await reconcile_test_payments(self.context)
        self.service.refresh_details.assert_called_once()
        self.assertEqual(self.service.refresh_details.call_args.args[:2], ('order-1', 10))
        self.context.bot.send_message.assert_awaited_once()
        self.assertIn('Оплата принята', self.context.bot.send_message.call_args.kwargs['text'])
        self.assertIn('&lt;Катя&gt;', self.context.bot.send_message.call_args.kwargs['text'])
        self.assertIn('payment_success:order-1', self.sent)
        await reconcile_test_payments(self.context)
        self.context.bot.send_message.assert_awaited_once()

    async def test_canceled_payment_sends_one_retry_message_with_tariff_button(self):
        self.pending.clear()
        self.canceled[:] = ['canceled-order']
        await reconcile_test_payments(self.context, check_pending=False)
        await reconcile_test_payments(self.context, check_pending=False)
        self.context.bot.send_message.assert_awaited_once()
        call = self.context.bot.send_message.await_args
        self.assertIn('Оплата не прошла', call.kwargs['text'])
        self.assertIn('Попробуй ещё раз', call.kwargs['text'])
        button = call.kwargs['reply_markup'].inline_keyboard[0][0]
        self.assertEqual(button.text, 'Посмотреть тарифы')
        self.assertEqual(button.web_app.url, 'https://example.org')
        self.assertIn('payment_canceled:canceled-order', self.sent)

    async def test_telegram_failure_retries_notice_without_regrant(self):
        self.context.bot.send_message.side_effect = RuntimeError('Telegram unavailable')
        with self.assertLogs('app.subscription.jobs', level='WARNING'):
            await reconcile_test_payments(self.context)
        self.assertFalse(self.sent)
        self.assertEqual(self.granted, ['order-1'])
        self.context.bot.send_message.side_effect = None
        await reconcile_test_payments(self.context)
        self.assertIn('payment_success:order-1', self.sent)
        self.service.refresh_details.assert_called_once()

    async def test_provider_failure_does_not_send_success_or_stop_other_notices(self):
        self.service.refresh_details.side_effect = RuntimeError('Provider unavailable')
        self.granted[:] = ['earlier-paid-order']
        with self.assertLogs('app.subscription.jobs', level='WARNING'):
            await reconcile_test_payments(self.context)
        self.assertNotIn('payment_success:order-1', self.sent)
        self.assertIn('payment_success:earlier-paid-order', self.sent)

    async def test_second_worker_skips_locked_delivery(self):
        self.repo.notification_lock.side_effect = lambda *args: nullcontext(False)
        await deliver_payment_notice(self.context, 10, 'order-1', at(13))
        self.context.bot.send_message.assert_not_awaited()
        self.assertFalse(self.sent)

    async def test_payment_confirmation_restores_full_reply_keyboard_once(self):
        await deliver_payment_notice(self.context, 10, 'order-1', at(13))
        await deliver_payment_notice(self.context, 10, 'order-1', at(13))
        self.context.bot.send_message.assert_awaited_once()
        keyboard = self.context.bot.send_message.await_args.kwargs['reply_markup']
        labels = [button.text for row in keyboard.keyboard for button in row]
        self.assertIn('САМ решу', labels)
        self.assertNotIn('🔒 Подобрать практику', labels)

    async def test_fast_and_periodic_workers_share_one_delivery(self):
        import asyncio
        from contextlib import asynccontextmanager
        mutex = asyncio.Lock()
        @asynccontextmanager
        async def locked(*args):
            async with mutex:
                yield True
        self.context.bot_data.pop('subscription_payment_service')
        self.pending.clear()
        self.granted[:] = ['order-1']
        with patch('app.subscription.jobs._notice_lock', locked):
            await asyncio.gather(reconcile_test_payments(self.context),
                                 reconcile_test_payments(self.context, user_ids={10}, check_pending=False))
        self.context.bot.send_message.assert_awaited_once()

    async def test_fast_delivery_never_checks_other_pending_payment(self):
        self.granted[:] = ['confirmed-order']
        await reconcile_test_payments(self.context, user_ids={10}, check_pending=False)
        self.service.refresh_details.assert_not_called()
        self.repo.touch_order_check.assert_not_called()
        self.assertIn('payment_success:confirmed-order', self.sent)

    async def test_periodic_worker_delivers_ready_notice_before_provider_request(self):
        self.granted[:] = ['confirmed-order']
        def check(*args):
            self.assertIn('payment_success:confirmed-order', self.sent)
        self.service.refresh_details.side_effect = check
        await reconcile_test_payments(self.context)
        self.service.refresh_details.assert_called_once()
        self.context.bot.send_message.assert_awaited_once()

    async def test_fast_delivery_does_not_wait_for_inflight_periodic_provider_call(self):
        import asyncio
        import threading
        entered, release = threading.Event(), threading.Event()
        def slow_check(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('Test did not release provider call')
        self.service.refresh_details.side_effect = slow_check
        periodic = asyncio.create_task(reconcile_test_payments(self.context))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            # A webhook commits this grant while another order's API call stalls.
            self.granted[:] = ['webhook-confirmed']
            await asyncio.wait_for(reconcile_test_payments(
                self.context, user_ids={10}, check_pending=False), timeout=1)
            self.assertIn('payment_success:webhook-confirmed', self.sent)
            self.assertFalse(periodic.done())
            self.service.refresh_details.assert_called_once()
        finally:
            release.set()
            await periodic
        self.context.bot.send_message.assert_awaited_once()

    async def test_allowlist_is_required(self):
        self.context.bot_data['subscription_test_users'] = set()
        await reconcile_test_payments(self.context)
        self.repo.payment_work.assert_not_called()
        self.service.refresh_details.assert_not_called()

    async def test_test_bot_without_allowlist_checks_only_enrolled_accounts(self):
        self.context.bot_data['subscription_test_users'] = None
        self.repo.enrolled_user_ids.return_value = [10]
        await reconcile_test_payments(self.context)
        self.repo.enrolled_user_ids.assert_called_once()
        self.repo.payment_work.assert_called_with(10)

    async def test_http_grant_is_delivered_without_provider_credentials(self):
        self.context.bot_data.pop('subscription_payment_service')
        self.pending.clear()
        self.granted[:] = ['already-committed']
        await reconcile_test_payments(self.context)
        self.assertIn('payment_success:already-committed', self.sent)


class ReminderWorkerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        onboarding = patch('app.onboarding.state.load_state', return_value=None)
        onboarding.start()
        self.addCleanup(onboarding.stop)
        self.repo = Mock()
        self.sent = set()
        self.repo.notification_lock.side_effect = lambda *args: nullcontext(True)
        self.repo.notification_sent.side_effect = lambda user, key: key in self.sent
        self.repo.mark_notification_sent.side_effect = lambda user, key, now: self.sent.add(key)
        self.trial = start_trial(at(1))
        self.state = Subscription(self.trial)
        self.repo.synchronize_access.return_value = self.state
        self.repo.get.return_value = self.state
        self.repo.reminder_profile.return_value = dict(chat_id=10, name='Катя', challenge=False,
            completions=4, has_favorites=False, filter_keys=['five', 'relax'])
        self.repo.restore_offer.return_value = None
        self.repo.old_user_reminder_context.return_value = (None, False)
        self.context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), bot_data={
            'subscription_repository': self.repo, 'subscription_test_users': {10},
            'subscription_miniapp_url': 'https://example.org'})

    async def test_old_user_reminders_reach_worker_and_are_not_sent_twice(self):
        from app.subscription.old_users.notifications import notification_schedule
        offer = launch_offer(at(1))
        self.repo.old_user_reminder_context.return_value = (offer, False)
        self.repo.get.return_value = self.repo.synchronize_access.return_value = Subscription(gift=offer.gift)
        for event in notification_schedule(offer):
            with self.subTest(kind=event.kind):
                self.context.bot.send_message.reset_mock()
                with patch('app.subscription.jobs.datetime') as clock:
                    clock.now.return_value = event.scheduled_at
                    clock.combine.side_effect = datetime.combine
                    await deliver_test_reminders(self.context)
                    await deliver_test_reminders(self.context)
                calls = self.context.bot.send_message.await_args_list
                self.assertEqual(len(calls), 2 if event.kind == 'gift_expired' else 1)
                self.assertIn(event.kind, ' '.join(self.sent))
                if event.kind == 'gift_expired':
                    self.assertEqual(calls[0].kwargs['reply_markup'].keyboard[0][0].text,
                                     'Практика дня')
                    self.assertNotIn('Только для своих', calls[0].kwargs['text'])
                    self.assertIn('<b>Только для своих</b>', calls[1].kwargs['text'])
                    self.assertEqual(calls[1].kwargs['parse_mode'], 'HTML')
                else:
                    self.assertTrue(calls[0].kwargs['reply_markup'].inline_keyboard)

    async def test_pending_checkout_before_send_suppresses_old_user_sales(self):
        offer = launch_offer(at(1))
        state = Subscription(gift=offer.gift)
        moment = offer.gift.ends_at - timedelta(days=3) + timedelta(hours=13)
        event = due_reminders(state, moment, old_user_offer=offer)[0]
        self.repo.get.return_value = state
        self.repo.old_user_reminder_context.return_value = (offer, True)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await _send_reminder(self.context, 10, event, self.repo.reminder_profile.return_value, moment)
        self.context.bot.send_message.assert_not_awaited()

    async def test_purchase_before_send_suppresses_old_user_sales(self):
        offer = launch_offer(at(1))
        moment = offer.gift.ends_at - timedelta(days=3) + timedelta(hours=13)
        event = due_reminders(Subscription(gift=offer.gift), moment, old_user_offer=offer)[0]
        paid = purchased_period('month', at(2), trial_ends_at=offer.gift.ends_at)
        self.repo.get.return_value = Subscription(gift=offer.gift, paid=paid)
        self.repo.old_user_reminder_context.return_value = (replace(offer, used_at=at(2)), False)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await _send_reminder(self.context, 10, event, self.repo.reminder_profile.return_value, moment)
        self.context.bot.send_message.assert_not_awaited()

    async def test_three_day_reminder_is_sent_once_at_13_moscow(self):
        moment = at(12, 13)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await deliver_test_reminders(self.context)
            await deliver_test_reminders(self.context)
        self.context.bot.send_message.assert_awaited_once()
        text = self.context.bot.send_message.call_args.kwargs['text']
        self.assertIn('через 3 дня', text)
        self.assertIn('trial_three_days', next(iter(self.sent)))

    async def test_prepaid_trial_activation_is_sent_once_without_tariff_button(self):
        paid = purchased_period('month', at(2), trial_ends_at=self.trial.ends_at)
        self.state = Subscription(self.trial, paid)
        self.repo.synchronize_access.return_value = self.state
        self.repo.get.return_value = self.state
        moment = at(15, 8)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await deliver_test_reminders(self.context)
            await deliver_test_reminders(self.context)
        self.context.bot.send_message.assert_awaited_once()
        call = self.context.bot.send_message.call_args
        self.assertIn('Пробный период завершился', call.kwargs['text'])
        self.assertIn('Подписка активна', call.kwargs['text'])
        self.assertIsNone(call.kwargs['reply_markup'])

    async def test_challenge_profile_receives_challenge_paid_reminder(self):
        paid = purchased_period('month', at(1))
        self.state = Subscription(paid=paid)
        self.repo.synchronize_access.return_value = self.state
        self.repo.get.return_value = self.state
        self.repo.reminder_profile.return_value['challenge'] = True
        moment = paid.ends_at - timedelta(days=1) + timedelta(hours=19)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await deliver_test_reminders(self.context)
        self.context.bot.send_message.assert_awaited_once()
        text = self.context.bot.send_message.call_args.kwargs['text']
        self.assertIn('последний день полного доступа', text)
        self.assertNotIn('рассылка по расписанию', text)

    async def test_challenge_profile_receives_universal_trial_copy(self):
        self.repo.reminder_profile.return_value['challenge'] = True
        moment = at(12, 13)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await deliver_test_reminders(self.context)
        self.context.bot.send_message.assert_awaited_once()
        text = self.context.bot.send_message.call_args.kwargs['text']
        self.assertIn('Полный доступ закончится через 3 дня', text)
        self.assertNotIn('расписание', text)

    async def test_challenge_profile_skips_trial_followup(self):
        self.repo.reminder_profile.return_value['challenge'] = True
        moment = at(22, 10)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await deliver_test_reminders(self.context)
        self.context.bot.send_message.assert_not_awaited()

    async def test_renewal_before_delivery_suppresses_old_reminder(self):
        moment = at(12, 13)
        old = due_reminders(self.state, moment)[0]
        paid = purchased_period('month', at(11), trial_ends_at=self.trial.ends_at)
        self.repo.get.return_value = Subscription(self.trial, paid)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await _send_reminder(self.context, 10, old, self.repo.reminder_profile.return_value, moment)
        self.context.bot.send_message.assert_not_awaited()
        self.assertFalse(self.sent)

    async def test_expiry_updates_keyboard_and_adds_tariff_button_once(self):
        moment = at(15, 8)
        event = due_reminders(self.state, moment)[0]
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await _send_reminder(self.context, 10, event, self.repo.reminder_profile.return_value, moment)
            await _send_reminder(self.context, 10, event, self.repo.reminder_profile.return_value, moment)
        self.assertEqual(self.context.bot.send_message.await_count, 2)
        self.assertEqual(len(self.sent), 2)
        first, second = self.context.bot.send_message.await_args_list
        self.assertIn('Пробный период завершён', first.kwargs['text'])
        self.assertEqual('Практика дня', first.kwargs['reply_markup'].keyboard[0][0].text)
        self.assertEqual(second.kwargs['reply_markup'].inline_keyboard[0][0].text, 'Посмотреть тарифы')
        self.assertEqual(second.kwargs['reply_markup'].inline_keyboard[0][0].to_dict()['style'],
                         'primary')

    async def test_expiry_without_checkout_sends_only_free_keyboard(self):
        self.context.bot_data['subscription_miniapp_url'] = ''
        moment = at(15, 8)
        event = due_reminders(self.state, moment)[0]
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await _send_reminder(self.context, 10, event, self.repo.reminder_profile.return_value, moment)
        self.context.bot.send_message.assert_awaited_once()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.context.bot.send_message.call_args.kwargs['reply_markup'].keyboard[0][0].text,
                         'Практика дня')

    async def test_restore_offer_contains_yes_no_and_is_not_resent(self):
        paid_start = at(15)
        paid = purchased_period('month', at(3), trial_ends_at=paid_start)
        self.repo.synchronize_access.return_value = Subscription(self.trial, paid)
        self.repo.restore_offer.return_value = (10, '09:30', paid_start)
        moment = at(15, 9)
        with patch('app.subscription.jobs.datetime') as clock:
            clock.now.return_value = moment
            clock.combine.side_effect = datetime.combine
            await deliver_test_reminders(self.context)
            await deliver_test_reminders(self.context)
        self.context.bot.send_message.assert_awaited_once()
        labels = [button.text for button in self.context.bot.send_message.call_args.kwargs[
            'reply_markup'].inline_keyboard[0]]
        self.assertEqual(labels, ['Да', 'Не сейчас'])
