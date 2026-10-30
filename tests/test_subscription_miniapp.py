"""Telegram authentication tests with a deliberately fake bot token."""
import hashlib
import hmac
import json
import unittest
from io import BytesIO
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import uuid4
from urllib.parse import urlencode

from app.miniapp.auth import authenticate
from app.miniapp.server import (MiniApp, create_hosted_test_app, create_preview_app,
                                create_test_app)
from app.miniapp.gateway import TestGateway
import httpx
from app.subscription.tariff import MOSCOW
from app.subscription.old_users.repository import CheckoutProfile
from app.subscription.old_users.rules import launch_offer


class MiniAppAuthTest(unittest.TestCase):
    token = '123:fake-test-token'
    now = 1791892800

    def signed(self, **changes):
        fields = {'auth_date': str(self.now), 'user': json.dumps({'id': 10}), 'query_id': 'abc'}
        fields.update(changes)
        text = '\n'.join('{}={}'.format(k, v) for k, v in sorted(fields.items()))
        key = hmac.new(b'WebAppData', self.token.encode(), hashlib.sha256).digest()
        fields['hash'] = hmac.new(key, text.encode(), hashlib.sha256).hexdigest()
        return urlencode(fields)

    def test_signed_allowlisted_user(self):
        self.assertEqual(authenticate(self.signed(), self.token, self.now, {10}), 10)
        self.assertEqual(authenticate(self.signed(), self.token, self.now, None), 10)

    def test_tampered_user_and_wrong_bot(self):
        for data, token in ((self.signed().replace('abc', 'changed'), self.token),
                            (self.signed(), '999:another-bot')):
            with self.assertRaises(ValueError):
                authenticate(data, token, self.now, {10})

    def test_expired_future_duplicate_and_nonallowed(self):
        cases = [self.signed(auth_date=str(self.now - 3601)),
                 self.signed(auth_date=str(self.now + 31)),
                 self.signed() + '&auth_date=1', self.signed(user=json.dumps({'id': 11})),
                 self.signed(user=json.dumps({'id': True})), '', 'hash=x', 'broken']
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                authenticate(data, self.token, self.now, {10})


class MiniAppHTTPTest(unittest.TestCase):
    def setUp(self):
        self.repo, self.payments = Mock(), Mock()
        self.payments.allowed_tariffs = None
        self.repo.checkout_profile.return_value = CheckoutProfile('user@example.org', None, None, None)
        self.repo.open_order_id.return_value = None
        self.auth = MiniAppAuthTest()
        self.app = MiniApp(repository=self.repo, payments=self.payments,
                           bot_token=self.auth.token, allowed_users={10},
                           clock=lambda: datetime.fromtimestamp(self.auth.now, MOSCOW))

    def request(self, path, data=None, *, app=None, method='POST', content_type='application/json'):
        body = json.dumps(data if data is not None else {'init_data': self.auth.signed()}).encode()
        env = {'PATH_INFO': path, 'REQUEST_METHOD': method, 'CONTENT_TYPE': content_type,
               'CONTENT_LENGTH': str(len(body)), 'wsgi.input': BytesIO(body)}
        response = []
        payload = b''.join((app or self.app)(env, lambda status, headers: response.append((status, headers))))
        return response[0][0], payload

    def test_preview_shows_prices_but_cannot_create_payments(self):
        preview = create_preview_app()
        status, body = self.request('/api/session', {}, app=preview)
        self.assertEqual(status, '200 OK')
        self.assertEqual([x['final_price'] for x in json.loads(body)['tariffs']],
                         [35000,80000,140000,250000])
        status, _ = self.request('/api/payments', {}, app=preview)
        self.assertTrue(status.startswith('403'))

    def test_old_user_preview_shows_special_prices_but_cannot_pay(self):
        offer = launch_offer(datetime.fromtimestamp(self.auth.now, MOSCOW))
        preview = MiniApp(preview=True, preview_offer=offer,
                          clock=lambda: datetime.fromtimestamp(self.auth.now, MOSCOW))
        status, body = self.request('/api/session', {}, app=preview)
        data = json.loads(body)
        self.assertEqual(status, '200 OK')
        self.assertEqual([x['final_price'] for x in data['tariffs']],
                         [25000, 60000, 100000, 180000])
        self.assertIsNotNone(data['offer_ends_on'])
        status, _ = self.request('/api/payments', {}, app=preview)
        self.assertEqual(status, '403 Forbidden')

    def test_forged_user_never_reaches_database(self):
        status, _ = self.request('/api/session', {'init_data': 'hash=forged'})
        self.assertTrue(status.startswith('401'))
        self.repo.checkout_profile.assert_not_called()

    def test_gateway_preserves_preview_and_authenticates_test_requests(self):
        def forward(request):
            self.assertEqual(request.url.host, 'test.example.org')
            self.assertNotIn('cookie', request.headers)
            status, body = self.request(request.url.path, json.loads(request.content))
            return httpx.Response(int(status.split()[0]), content=body)
        gateway = TestGateway(MiniApp(preview=True), 'https://test.example.org',
                              transport=httpx.MockTransport(forward))
        status, body = self.request('/api/session', app=gateway)
        self.assertTrue(json.loads(body)['preview'])
        status, body = self.request('/api/payments', app=gateway)
        self.assertEqual(status, '403 Forbidden')
        self.payments.checkout.assert_not_called()
        status, body = self.request('/test-api/session', app=gateway)
        self.assertEqual(status, '200 OK')
        self.assertFalse(json.loads(body)['preview'])
        self.repo.reset_mock()
        status, body = self.request('/test-api/session', {'init_data': 'forged'}, app=gateway)
        self.assertEqual(status, '401 Unauthorized')
        self.repo.checkout_profile.assert_not_called()

    def test_gateway_outage_does_not_break_preview(self):
        def unavailable(request):
            raise httpx.ConnectError('private error')
        gateway = TestGateway(MiniApp(preview=True), 'https://test.example.org',
                              transport=httpx.MockTransport(unavailable))
        status, body = self.request('/test-api/session', app=gateway)
        self.assertEqual(status, '503 Service Unavailable')
        self.assertNotIn(b'private error', body)
        status, body = self.request('/api/session', app=gateway)
        self.assertTrue(json.loads(body)['preview'])
        status, body = self.request('/test-api/../me', app=gateway)
        self.assertEqual(status, '404 Not Found')

    def test_static_paths_do_not_expose_repository_files(self):
        for path in ('/../.env', '/static/../../.env', '/server.py'):
            status, _ = self.request(path, method='GET')
            self.assertTrue(status.startswith('404'))
        status, body = self.request('/', method='GET')
        self.assertEqual(status, '200 OK')
        self.assertIn('Email для чека'.encode(), body)

    def test_special_offer_ui_places_terms_below_tariffs(self):
        _, html = self.request('/', method='GET')
        _, script = self.request('/app.js', method='GET')
        page = html.decode()
        client = script.decode()
        self.assertLess(page.index('id="early-user-note"'), page.index('id="tariffs"'))
        self.assertIn('Скидки только для самых первых пользователей', page)
        self.assertLess(page.index('id="tariffs"'), page.index('id="period-note"'))
        self.assertLess(page.index('id="tariffs"'), page.index('id="offer-ends"'))
        self.assertLess(page.index('id="period-note"'), page.index('id="email-field"'))
        self.assertLess(page.index('id="email-field"'), page.index('class="promo-field"'))
        self.assertLess(page.index('class="promo-field"'), page.index('class="paybar"'))
        self.assertNotIn('id="resume" class="secondary" target="_blank"', page)
        self.assertNotIn('tg.openLink(confirmationUrl)', client)
        self.assertIn('window.location.assign(confirmationUrl)', client)
        self.assertNotIn('id="back"', page)
        self.assertNotIn('replace_open_order', client)
        self.assertIn("status('Оплата пока не завершена'", client)
        self.assertIn("launchParams.get('tgWebAppStartParam')", client)
        self.assertIn('после этого можно будет оформить новую оплату', client)
        self.assertNotIn("status('Оплата отменена'", client)
        self.assertIn("data.status === 'canceled'", client)
        self.assertIn("$('payment-status').hidden = true; $('checkout').hidden = false;", client)
        self.assertIn('Специальные цены действуют до ${date} включительно\\n'
                      'только на первую покупку', client)
        self.assertIn("basePrice.className = 'tariff-base-price'", client)
        self.assertIn("rows.push(['tariff-monthly', monthly || '\\u00a0'])", client)
        self.assertIn("basePrice.className = 'pay-base-price'", client)
        self.assertNotIn("promo-field", client)
        self.assertIn("if (months === 1) return '';", client)

    def test_session_has_server_tariffs_and_saved_email(self):
        status, body = self.request('/api/session')
        data = json.loads(body)
        self.assertEqual(status, '200 OK')
        self.assertEqual(data['email'], 'user@example.org')
        self.assertEqual(data['tariffs'][0]['days'], 30)
        self.repo.checkout_profile.assert_called_once_with(10)

    def test_old_user_session_shows_special_prices_and_offer_end(self):
        offer = launch_offer(datetime.fromtimestamp(self.auth.now, MOSCOW))
        self.repo.checkout_profile.return_value = CheckoutProfile(
            'user@example.org', None, None, offer)
        status, body = self.request('/api/session')
        data = json.loads(body)
        self.assertEqual(status, '200 OK')
        self.assertEqual([(item['base_price'], item['final_price']) for item in data['tariffs']],
                         [(35000,25000), (80000,60000), (140000,100000), (250000,180000)])
        self.assertIsNotNone(data['offer_ends_on'])

    def test_live_run_shows_only_month_and_real_charge_warning(self):
        self.payments.allowed_tariffs = frozenset({'month'})
        status, body = self.request('/api/session')
        data = json.loads(body)
        self.assertEqual(status, '200 OK')
        self.assertEqual([t['code'] for t in data['tariffs']], ['month'])
        self.assertEqual(data['tariffs'][0]['final_price'], 35000)
        self.assertIn('Настоящее списание 350 ₽', data['note'])

    def test_success_is_returned_after_service_grant(self):
        order_id = str(uuid4())
        end = datetime(2026, 11, 12, tzinfo=MOSCOW)
        self.repo.checkout_profile.return_value = CheckoutProfile('user@example.org', None, end, None)
        self.payments.refresh_details.return_value = {'status': 'succeeded'}
        status, body = self.request('/api/payments/' + order_id)
        self.assertEqual(status, '200 OK')
        self.assertEqual(json.loads(body)['ends_on'], '2026-11-11')
        self.assertEqual(self.payments.refresh_details.call_args.args[1], 10)

    def test_client_amount_is_never_forwarded(self):
        order_id = str(uuid4())
        self.payments.checkout.return_value = (order_id, {'confirmation': {'confirmation_url':'https://example.org'}})
        status, _ = self.request('/api/payments', {'init_data': self.auth.signed(), 'order_id':order_id,
            'tariff_code':'month', 'email':'user@example.org', 'amount':1,
            'final_price':35000, 'user_id':999})
        self.assertEqual(status, '200 OK')
        args = self.payments.checkout.call_args.args
        self.assertEqual(args[1:4], (10, 'month', 'user@example.org'))
        self.assertEqual(self.payments.checkout.call_args.kwargs['expected_final_price'], 35000)

    def test_provider_error_does_not_leak_details(self):
        self.repo.checkout_profile.side_effect = RuntimeError('SECRET DATABASE DETAIL')
        status, body = self.request('/api/session')
        self.assertTrue(status.startswith('503'))
        self.assertNotIn(b'SECRET', body)


class TestServerSetupTest(unittest.TestCase):
    def settings(self):
        return dict(SUBSCRIPTION_TEST_ENABLED='true', ENV_FILE='test/.env.test',
                    BOT_TOKEN='123:fake',
                    SUBSCRIPTION_TEST_USERS='10', SUBSCRIPTION_TEST_DATABASE='yogadaily_test',
                    SUBSCRIPTION_MINIAPP_URL='https://example.org/pay',
                    SUBSCRIPTION_PAYMENT_RETURN_URL='https://t.me/TestYogaBot?startapp=payment',
                    SUBSCRIPTION_YOOKASSA_TEST_SHOP_ID='123',
                    SUBSCRIPTION_YOOKASSA_TEST_SECRET_KEY='fake')

    def test_missing_or_wrong_environment_never_opens_database(self):
        factory, provider = Mock(), Mock()
        for values in ({}, dict(self.settings(), ENV_FILE='.env'),
                       dict(self.settings(), SUBSCRIPTION_TEST_DATABASE='production'),
                       dict(self.settings(), SUBSCRIPTION_YOOKASSA_TEST_SECRET_KEY='')):
            with self.subTest(values=values), self.assertRaises(ValueError):
                create_test_app(values, factory, provider=provider)
        factory.assert_not_called()
        provider.verify_test_store.assert_not_called()

    def test_test_database_and_shop_checked_before_serving(self):
        factory, provider = Mock(), Mock(expected_test=True)
        with patch('data.subscription_repository.SubscriptionRepository') as repository_class:
            app = create_test_app(self.settings(), factory, provider=provider)
            repository_class.return_value.verify_test_database.assert_called_once_with('yogadaily_test')
            provider.verify_test_store.assert_called_once()
            self.assertEqual(app.allowed_users, {10})
            self.assertEqual(app.return_url, 'https://t.me/TestYogaBot?startapp=payment')
            self.assertFalse(app.preview)

    def test_return_url_must_be_the_app_or_telegram_main_app(self):
        factory, provider = Mock(), Mock(expected_test=True)
        provider.verify_test_store.return_value = None
        for return_url in ('http://t.me/TestYogaBot?startapp=payment',
                           'https://evil.example/return',
                           'https://t.me/TestYogaBot'):
            with self.subTest(return_url=return_url), self.assertRaises(ValueError):
                create_test_app(dict(self.settings(), SUBSCRIPTION_PAYMENT_RETURN_URL=return_url),
                                factory, provider=provider)

    def test_hosted_runtime_requires_separate_explicit_switch(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            create_hosted_test_app()
        with patch.dict('os.environ', {'SUBSCRIPTION_HOSTED_TEST_ENABLED': 'true'}, clear=True), \
                patch('app.miniapp.server.create_test_app', return_value='app') as create:
            self.assertEqual(create_hosted_test_app(), 'app')
            self.assertEqual(create.call_args.args[0]['SUBSCRIPTION_HOSTED_TEST_ENABLED'], 'true')
