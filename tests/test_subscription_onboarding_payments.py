"""Durable onboarding branches after checkout and the free navigation screen."""
import unittest
from datetime import datetime
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.onboarding import messages
from app.onboarding.flow import continue_after_subscription_payment, _finish_second_message, handle_reply
from app.subscription.access import Subscription
from app.subscription.demo import start_trial
from app.subscription.tariff import MOSCOW, purchased_period


class CheckoutOnboardingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = dict(user_id=1, chat_id=10, step='subscription', entered_at=1000)
        self.repo = Mock()
        self.repo.enrolled_user_ids.return_value = [1]
        self.sent = set()
        self.repo.notification_sent.side_effect = lambda user, key: key in self.sent
        self.repo.mark_notification_sent.side_effect = lambda user, key, now: self.sent.add(key)
        self.repo.get.return_value = Subscription(paid=purchased_period('month', datetime.now(MOSCOW)))
        self.context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), bot_data={
            'subscription_repository': self.repo, 'subscription_test_users': None,
            'subscription_miniapp_url': 'https://example.org/?test=1'})

    async def test_success_waits_for_notice_then_advances_once(self):
        self.repo.onboarding_payment_results.return_value = [('order', 'succeeded')]
        with patch('app.onboarding.flow.load_state', side_effect=lambda _: dict(self.state)), patch(
                'app.onboarding.flow._send_step', new_callable=AsyncMock) as send:
            send.side_effect = lambda context, state: self.state.update(state)
            await continue_after_subscription_payment(self.context, 1)
            send.assert_not_awaited()
            self.sent.add('payment_success:order')
            await continue_after_subscription_payment(self.context, 1)
            await continue_after_subscription_payment(self.context, 1)
            send.assert_awaited_once()
            self.assertEqual(self.state['step'], 'schedule_offer')

    async def test_active_free_button_delivers_notice_before_schedule_and_only_once(self):
        self.repo.onboarding_payment_results.return_value = [('order','succeeded')]
        self.repo.notification_lock.side_effect = lambda *args: nullcontext(True)
        self.repo.payment_work.side_effect = lambda user: (['other-pending'],
            [] if 'payment_success:order' in self.sent else ['order'])
        self.repo.payment_notice.return_value = (10, '', self.repo.get.return_value.paid.ends_at)
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
            effective_message=SimpleNamespace(text='Продолжить бесплатно'))
        sequence = []
        async def notice(*args, **kwargs):
            sequence.append('notice')
        async def screen(context, state):
            self.assertIn('payment_success:order', self.sent)
            sequence.append('schedule')
            self.state.update(state)
        self.context.bot.send_message.side_effect = notice
        with patch('app.onboarding.flow.load_state', side_effect=lambda _: dict(self.state)), patch(
                'app.onboarding.flow._send_step', side_effect=screen):
            await handle_reply(update, self.context)
            await handle_reply(update, self.context)
        self.assertEqual(sequence, ['notice','schedule'])
        self.assertEqual(self.state['step'], 'schedule_offer')

    async def test_active_free_button_does_not_advance_when_notice_fails(self):
        self.repo.onboarding_payment_results.return_value = [('order','succeeded')]
        self.repo.payment_work.return_value = ([],['order'])
        self.repo.notification_lock.side_effect = lambda *args: nullcontext(True)
        self.repo.payment_notice.return_value = (10, '', self.repo.get.return_value.paid.ends_at)
        self.context.bot.send_message.side_effect = RuntimeError('Telegram unavailable')
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
            effective_message=SimpleNamespace(text='Продолжить бесплатно'))
        with patch('app.onboarding.flow.load_state', return_value=self.state), patch(
                'app.onboarding.flow._send_step', new_callable=AsyncMock) as send, self.assertLogs(
                    'app.subscription.jobs', level='WARNING'):
            await handle_reply(update, self.context)
            send.assert_not_awaited()
        self.assertEqual(self.state['step'], 'subscription')
        self.assertFalse(self.sent)

    async def test_unpaid_free_button_keeps_free_completion(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
            effective_message=SimpleNamespace(text='Продолжить бесплатно'))
        with patch('app.onboarding.flow.load_state', return_value=self.state), patch(
                'app.onboarding.flow._subscription_variant', new_callable=AsyncMock, return_value='used'), patch(
                'app.onboarding.flow._finish', new_callable=AsyncMock) as finish:
            await handle_reply(update, self.context)
        finish.assert_awaited_once()

    async def test_old_trial_button_cannot_skip_paid_confirmation(self):
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
            effective_message=SimpleNamespace(text='Начать 14 дней бесплатно'))
        with patch('app.onboarding.flow.load_state', return_value=self.state), patch(
                'app.subscription.jobs.reconcile_test_payments', new_callable=AsyncMock) as retry, patch(
                'app.onboarding.flow._transition', new_callable=AsyncMock) as transition:
            await handle_reply(update, self.context)
        retry.assert_awaited_once_with(self.context, user_ids={1}, check_pending=False)
        transition.assert_not_awaited()
        self.repo.begin_fast_trial.assert_not_called()

    async def test_active_unpaid_trial_can_continue_normally(self):
        self.repo.get.return_value = Subscription(trial=start_trial(datetime.now(MOSCOW)))
        update = SimpleNamespace(effective_user=SimpleNamespace(id=1),
            effective_message=SimpleNamespace(text='Начать 14 дней бесплатно'))
        with patch('app.onboarding.flow.load_state', return_value=self.state), patch(
                'app.onboarding.flow._transition', new_callable=AsyncMock) as transition:
            await handle_reply(update, self.context)
        self.assertEqual(transition.await_args.args[2], 'schedule_offer')

    async def test_canceled_keeps_retry_and_free_buttons_and_does_not_repeat(self):
        self.repo.onboarding_payment_results.return_value = [('order', 'canceled')]
        with patch('app.onboarding.flow.load_state', return_value=self.state), patch(
                'app.onboarding.flow._send_step', new_callable=AsyncMock) as send:
            await continue_after_subscription_payment(self.context, 1)
            await continue_after_subscription_payment(self.context, 1)
            send.assert_not_awaited()
        self.assertEqual(self.context.bot.send_message.await_count, 2)
        call, tariffs = self.context.bot.send_message.await_args_list
        self.assertIn('Оплата не завершена', call.args[1])
        self.assertEqual([b.text for row in call.kwargs['reply_markup'].keyboard for b in row],
                         ['Продолжить бесплатно'])
        self.assertEqual(tariffs.kwargs['reply_markup'].inline_keyboard[0][0].web_app.url,
                         'https://example.org/?test=1')
        self.assertEqual(self.state['step'], 'subscription')

    async def test_pending_or_completed_onboarding_does_not_advance(self):
        self.repo.onboarding_payment_results.return_value = []
        with patch('app.onboarding.flow.load_state', return_value=self.state):
            await continue_after_subscription_payment(self.context, 1)
            self.state['step'] = 'complete'
            await continue_after_subscription_payment(self.context, 1)
        self.context.bot.send_message.assert_not_awaited()
        self.repo.onboarding_payment_results.assert_called_once()

    async def test_failed_transition_remains_retryable(self):
        self.repo.onboarding_payment_results.return_value = [('order', 'succeeded')]
        self.sent.add('payment_success:order')
        with patch('app.onboarding.flow.load_state', return_value=self.state), patch(
                'app.onboarding.flow.save_state') as save, patch(
                'app.onboarding.flow._send_step', new_callable=AsyncMock, side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                await continue_after_subscription_payment(self.context, 1)
            save.assert_not_called()
        self.assertEqual(self.state['step'], 'subscription')

    async def test_free_completion_has_only_free_navigation_and_keyboard(self):
        self.state['step'] = 'location'
        self.repo.get.return_value = Subscription()
        self.context.bot.send_message.return_value = SimpleNamespace(message_id=123)
        with patch('app.onboarding.flow.load_state', return_value=self.state), patch(
                'app.onboarding.flow.save_state'), patch('data.db.mark_reply_keyboard_version'), patch(
                'app.onboarding.flow._start_pending_challenge', new_callable=AsyncMock):
            await _finish_second_message(self.context, self.state)
        call = self.context.bot.send_message.await_args
        self.assertEqual(call.args[1], messages.COMPLETE_FREE)
        self.assertEqual([b.text for row in call.kwargs['reply_markup'].keyboard for b in row],
                         ['Практика дня', '🔒 Подобрать практику'])
        self.assertIn('<blockquote expandable>', call.args[1])
        self.assertNotIn('ленивые дни', call.args[1])
