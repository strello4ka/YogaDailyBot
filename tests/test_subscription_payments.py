"""Payment boundaries without network calls, secrets or a database."""
import json
import unittest
from urllib.parse import urlparse, parse_qs
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import httpx

from app.payments.service import PaymentService, new_order, normalize_email, verify_payment
from app.payments.yookassa import YooKassaLiveClient, YooKassaTestClient
from app.subscription.tariff import MOSCOW
from app.subscription.old_users.prices import checkout_price
from app.subscription.old_users.rules import launch_offer
from data.subscription_repository import SubscriptionRepository


NOW = datetime(2026, 10, 13, 23, tzinfo=MOSCOW)


class PaymentsTest(unittest.TestCase):
    def setUp(self):
        self.order = replace(new_order(uuid4(), 10, 'month', 'user@example.org', NOW),
                             provider_payment_id=str(uuid4()))
        self.payment = {'id': self.order.provider_payment_id, 'test': True,
                        'metadata': {'order_id': self.order.order_id},
                        'amount': {'value': '350.00', 'currency': 'RUB'},
                        'status': 'succeeded', 'paid': True}

    def test_server_prices_and_email(self):
        self.assertEqual(self.order.amount, '350.00')
        self.assertEqual(normalize_email(' user@example.org '), 'user@example.org')
        for bad in ('', 'a@b', 'a\nb@example.org', None):
            with self.assertRaises(ValueError):
                normalize_email(bad)

    def test_only_matching_test_payment_can_succeed(self):
        self.assertEqual(verify_payment(self.order, self.payment), 'succeeded')
        for patch in ({'test': False}, {'paid': False}, {'id': str(uuid4())},
                      {'metadata': {}}, {'status': 'unknown'},
                      {'amount': {'value': 'NaN', 'currency': 'RUB'}},
                      {'amount': {'value': '350', 'currency': 'USD'}},
                      {'amount': {'value': '1.00', 'currency': 'RUB'}}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                verify_payment(self.order, dict(self.payment, **patch))

    def test_live_payment_requires_live_provider_and_matching_payment(self):
        live_payment = dict(self.payment, test=False)
        self.assertEqual(verify_payment(self.order, live_payment,
                                        expected_test=False), 'succeeded')
        with self.assertRaises(ValueError):
            verify_payment(self.order, self.payment, expected_test=False)
        repository, provider = Mock(), Mock(expected_test=False)
        repository.get_order.return_value = self.order
        provider.get_payment.return_value = live_payment
        self.assertEqual(PaymentService(repository, provider).refresh(
            self.order.order_id, 10, NOW), 'succeeded')
        repository.grant_order.assert_called_once()

    def test_pending_and_canceled_do_not_grant(self):
        for status in ('pending', 'waiting_for_capture', 'canceled'):
            repo, provider = Mock(), Mock(expected_test=True)
            repo.get_order.return_value = self.order
            provider.get_payment.return_value = dict(self.payment, status=status, paid=False)
            self.assertEqual(PaymentService(repo, provider).refresh(self.order.order_id, 10, NOW), status)
            repo.grant_order.assert_not_called()

    def test_foreign_order_is_not_looked_up_at_provider(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.get_order.return_value = None
        with self.assertRaises(LookupError):
            PaymentService(repo, provider).refresh(self.order.order_id, 11, NOW)
        provider.get_payment.assert_not_called()

    def test_creation_retry_reuses_attached_payment(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.get_order.return_value = self.order
        provider.get_payment.return_value = self.payment
        result = PaymentService(repo, provider).create(
            self.order.order_id, 10, 'month', self.order.email, 'https://example.org', NOW)
        self.assertEqual(result, self.payment)
        provider.create_payment.assert_not_called()
        repo.save_order.assert_not_called()

    def test_different_browser_order_resumes_existing_checkout(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.payment_creation_lock.return_value = nullcontext()
        repo.open_order_id.return_value = self.order.order_id
        result = PaymentService(repo, provider).checkout(
            str(uuid4()), 10, 'year', self.order.email, 'https://example.org', NOW)
        self.assertEqual(result, (self.order.order_id, None))
        provider.create_payment.assert_not_called()
        repo.save_order.assert_not_called()

    def test_explicit_tariff_change_supersedes_old_checkout_and_creates_selected_one(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.payment_creation_lock.return_value = nullcontext()
        repo.open_order_id.return_value = self.order.order_id
        new_id = str(uuid4())
        service = PaymentService(repo, provider)
        service.create = Mock(return_value={'id': 'new-payment'})
        result = service.checkout(new_id, 10, 'quarter', self.order.email,
                                  'https://example.org', NOW,
                                  replace_open_order=True)
        self.assertEqual(result, (new_id, {'id': 'new-payment'}))
        repo.supersede_order.assert_called_once_with(self.order.order_id, 10, NOW)
        service.create.assert_called_once_with(new_id, 10, 'quarter', self.order.email,
                                               'https://example.org', NOW,
                                               expected_final_price=None)

    def test_pending_payment_offers_existing_confirmation_url(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.get_order.return_value = self.order
        provider.get_payment.return_value = dict(self.payment, status='pending', paid=False,
            confirmation={'confirmation_url': 'https://example.org/existing-payment'})
        result = PaymentService(repo, provider).refresh_details(self.order.order_id, 10, NOW)
        self.assertEqual(result, {'status': 'pending', 'confirmation_url': 'https://example.org/existing-payment'})
        repo.grant_order.assert_not_called()

    def test_creation_saves_before_provider_request_and_does_not_attach_bad_amount(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.get_order.return_value = None
        repo.checkout_price.return_value = (checkout_price('month', None, NOW), None)
        def create(order, return_url, now):
            repo.save_order.assert_called_once_with(order)
            return dict(self.payment, amount={'value': '1', 'currency': 'RUB'})
        provider.create_payment.side_effect = create
        with self.assertRaises(ValueError):
            PaymentService(repo, provider).create(
                self.order.order_id, 10, 'month', self.order.email, 'https://example.org', NOW)
        repo.attach_payment.assert_not_called()

    def test_timeout_keeps_saved_order_for_reconciliation(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.get_order.return_value = None
        repo.checkout_price.return_value = (checkout_price('month', None, NOW), None)
        provider.create_payment.side_effect = httpx.ReadTimeout('test timeout')
        with self.assertRaises(httpx.ReadTimeout):
            PaymentService(repo, provider).create(
                self.order.order_id, 10, 'month', self.order.email, 'https://example.org', NOW)
        repo.save_order.assert_called_once()
        repo.attach_payment.assert_not_called()
        repo.cancel_order.assert_not_called()

    def test_special_price_is_resolved_by_server_and_snapshotted(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.get_order.return_value = None
        offer = launch_offer(NOW)
        repo.checkout_price.return_value = (checkout_price('month', offer, NOW), offer.offer_ends)
        provider.create_payment.return_value = dict(
            self.payment, amount={'value': '250.00', 'currency': 'RUB'})
        PaymentService(repo, provider).create(
            self.order.order_id, 10, 'month', self.order.email, 'https://example.org', NOW,
            expected_final_price=25000)
        saved = repo.save_order.call_args.args[0]
        self.assertEqual((saved.base_price, saved.final_price), (35000, 25000))
        self.assertTrue(saved.special_offer_applied)
        self.assertEqual(saved.offer_ends_at_order, offer.offer_ends)

    def test_wakeup_follows_committed_grant_and_failure_does_not_change_success(self):
        repo, provider = Mock(), Mock(expected_test=True)
        repo.get_order.return_value = self.order
        provider.get_payment.return_value = self.payment
        repo.grant_order.return_value = True
        repo.signal_payment.side_effect = RuntimeError('notification unavailable')
        with self.assertLogs('app.payments.service', level='WARNING'):
            self.assertEqual(PaymentService(repo, provider).refresh(self.order.order_id, 10, NOW), 'succeeded')
        self.assertLess([c[0] for c in repo.method_calls].index('grant_order'),
                        [c[0] for c in repo.method_calls].index('signal_payment'))
        repo.signal_payment.reset_mock()
        repo.signal_payment.side_effect = None
        repo.grant_order.return_value = False
        self.assertEqual(PaymentService(repo, provider).refresh(self.order.order_id, 10, NOW), 'succeeded')
        repo.signal_payment.assert_called_once_with(10)

    def test_repeated_confirmation_has_no_second_write(self):
        factory = MagicMock()
        cursor = factory.return_value.cursor.return_value.__enter__.return_value
        end = NOW + timedelta(days=30)
        cursor.fetchone.side_effect = [(None, None, NOW, end, None, None, None),
                                      (NOW, 'succeeded', 30, self.order.provider_payment_id, 35000, False)]
        self.assertFalse(SubscriptionRepository(factory).grant_order(self.order, NOW))
        self.assertTrue(all(c.args[0].startswith('SELECT') for c in cursor.execute.call_args_list))

    def test_purchase_in_trial_starts_after_trial(self):
        factory = MagicMock()
        cursor = factory.return_value.cursor.return_value.__enter__.return_value
        trial_end = datetime(2026, 10, 15, tzinfo=MOSCOW)
        cursor.fetchone.side_effect = [(NOW - timedelta(days=12), trial_end, None, None,
                                        None, None, None),
                                      (None, 'pending', 30, self.order.provider_payment_id, 35000, False)]
        self.assertTrue(SubscriptionRepository(factory).grant_order(self.order, NOW))
        update = cursor.execute.call_args_list[-2]
        self.assertEqual(update.args[1][0], trial_end)
        self.assertEqual(update.args[1][1], trial_end + timedelta(days=30))
        self.assertEqual(update.args[1][3], 'trial_paid')

    def test_live_store_is_rejected_before_post(self):
        calls = []
        def transport(request):
            calls.append(request.method)
            return httpx.Response(200, json={'account_id': '123', 'test': False})
        client = YooKassaTestClient('123', 'fake', transport=httpx.MockTransport(transport))
        try:
            with self.assertRaises(ValueError):
                client.create_payment(self.order, 'https://example.org/return', NOW)
            self.assertEqual(calls, ['GET'])
        finally:
            client.close()

    def test_live_client_rejects_test_store_before_post(self):
        calls = []
        def transport(request):
            calls.append(request.method)
            return httpx.Response(200, json={'account_id': '123', 'test': True})
        client = YooKassaLiveClient('123', 'fake', transport=httpx.MockTransport(transport))
        try:
            with self.assertRaises(ValueError):
                client.create_payment(self.order, 'https://example.org/return', NOW)
            self.assertEqual(calls, ['GET'])
        finally:
            client.close()

    def test_live_client_checks_live_store_and_payment_mode(self):
        calls = []
        def transport(request):
            calls.append(request.method)
            if request.method == 'GET':
                return httpx.Response(200, json={'account_id': '123', 'test': False})
            return httpx.Response(200, json=dict(self.payment, test=False))
        client = YooKassaLiveClient('123', 'fake', transport=httpx.MockTransport(transport))
        try:
            result = client.create_payment(self.order, 'https://example.org/return', NOW)
            self.assertIs(result['test'], False)
            self.assertEqual(calls, ['GET', 'POST'])
        finally:
            client.close()

    def test_retry_uses_same_provider_key_and_server_amount(self):
        calls = []
        def transport(request):
            calls.append(request)
            if request.method == 'GET':
                return httpx.Response(200, json={'account_id': '123', 'test': True})
            return httpx.Response(200, json=self.payment)
        client = YooKassaTestClient('123', 'fake', transport=httpx.MockTransport(transport))
        try:
            for _ in range(2):
                client.create_payment(self.order, 'https://example.org/return?test=1&checkout_order=stale', NOW)
            posts = [r for r in calls if r.method == 'POST']
            self.assertEqual([r.headers['Idempotence-Key'] for r in posts], [self.order.order_id] * 2)
            payload = json.loads(posts[0].content)
            self.assertEqual(payload['amount']['value'], '350.00')
            self.assertTrue(payload['capture'])
            self.assertEqual(payload['metadata'], {
                'order_id': self.order.order_id,
                'receipt_service': 'yoga_daily_v1',
                'customer_email': 'user@example.org',
                'service_name': 'Доступ к YogaDailyBot на 30 дней',
            })
            returned = urlparse(payload['confirmation']['return_url'])
            self.assertEqual(parse_qs(returned.query)['checkout_order'], [self.order.order_id])
            self.assertEqual(parse_qs(returned.query)['test'], ['1'])
            with self.assertRaises(ValueError):
                client.create_payment(self.order, 'https://example.org/return', NOW + timedelta(days=1))
            self.assertEqual(len(calls), 4)
        finally:
            client.close()

    def test_telegram_main_app_return_carries_order_in_startapp(self):
        calls = []
        def transport(request):
            calls.append(request)
            if request.method == 'GET':
                return httpx.Response(200, json={'account_id': '123', 'test': True})
            return httpx.Response(200, json=self.payment)
        client = YooKassaTestClient('123', 'fake', transport=httpx.MockTransport(transport))
        try:
            client.create_payment(
                self.order, 'https://t.me/TestYogaBot?startapp=payment', NOW)
            payload = json.loads([request for request in calls if request.method == 'POST'][0].content)
            returned = urlparse(payload['confirmation']['return_url'])
            self.assertEqual(parse_qs(returned.query)['startapp'],
                             ['payment_' + self.order.order_id])
            self.assertNotIn('checkout_order', parse_qs(returned.query))
        finally:
            client.close()
