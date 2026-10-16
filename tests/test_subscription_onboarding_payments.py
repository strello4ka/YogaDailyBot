"""Durable onboarding branches after checkout and the free navigation screen."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.onboarding import messages
from app.onboarding.flow import continue_after_subscription_payment, _finish_second_message
from app.subscription.access import Subscription
from app.subscription.tariff import MOSCOW, purchased_period


class CheckoutOnboardingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = dict(user_id=1, chat_id=10, step='subscription', entered_at=1000)
        self.repo = Mock()
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
