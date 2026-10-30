"""Live-test opt-in and store isolation; no credentials, DB or network."""
import unittest
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4
from datetime import datetime

from app.payments.config import payment_settings
from app.payments.service import PaymentService, new_order
from app.subscription.tariff import MOSCOW
from app.miniapp.server import create_test_app
from data.subscription_repository import SubscriptionRepository


class LiveConfigTest(unittest.TestCase):
    def settings(self, **changes):
        values = dict(ENV_FILE='test/.env.test', SUBSCRIPTION_TEST_ENABLED='true',
                      SUBSCRIPTION_TEST_DATABASE='yogadaily_test', BOT_TOKEN='123:fake',
                      SUBSCRIPTION_MINIAPP_URL='https://example.org/?test=1',
                      SUBSCRIPTION_PAYMENT_MODE='live', SUBSCRIPTION_LIVE_PAYMENT_CONFIRM='1495040:350',
                      SUBSCRIPTION_YOOKASSA_LIVE_SHOP_ID='1495040',
                      SUBSCRIPTION_YOOKASSA_LIVE_SECRET_KEY='fake-live-secret')
        values.update(changes)
        return values

    def test_explicit_live_settings_and_secret_hidden(self):
        config = payment_settings(self.settings())
        self.assertTrue(config.live)
        self.assertEqual(config.scope, 'live:1495040')
        self.assertNotIn('fake-live-secret', repr(config))

    def test_wrong_or_incomplete_configuration_fails_closed(self):
        for change in (dict(ENV_FILE='.env'), dict(SUBSCRIPTION_TEST_ENABLED='false'),
                       dict(SUBSCRIPTION_TEST_DATABASE='production'),
                       dict(SUBSCRIPTION_PAYMENT_MODE='typo'),
                       dict(SUBSCRIPTION_LIVE_PAYMENT_CONFIRM=''),
                       dict(SUBSCRIPTION_YOOKASSA_LIVE_SHOP_ID='1497096'),
                       dict(SUBSCRIPTION_YOOKASSA_LIVE_SECRET_KEY='')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                payment_settings(self.settings(**change))

    def test_test_mode_does_not_fall_back_to_live_credentials(self):
        config = payment_settings(self.settings(SUBSCRIPTION_PAYMENT_MODE='test'))
        self.assertFalse(config.live)
        self.assertEqual(config.secret, '')

    def test_live_server_checks_real_store_and_uses_scoped_repository(self):
        provider = Mock(expected_test=False)
        with patch('data.subscription_repository.SubscriptionRepository') as repo:
            app = create_test_app(self.settings(), Mock(), provider=provider)
        self.assertEqual(repo.call_args.kwargs['payment_scope'], 'live:1495040')
        provider.verify_store.assert_called_once()
        provider.verify_test_store.assert_not_called()
        self.assertEqual(app.payments.allowed_tariffs, {'month'})

    def test_test_provider_cannot_be_injected_into_live_server(self):
        provider = Mock(expected_test=True)
        with patch('data.subscription_repository.SubscriptionRepository'), self.assertRaises(ValueError):
            create_test_app(self.settings(), Mock(), provider=provider)
        provider.verify_store.assert_not_called()

    def test_other_tariffs_never_reach_provider(self):
        repo, provider = Mock(), Mock(expected_test=False)
        service = PaymentService(repo, provider, allowed_tariffs=('month',))
        for method in (service.create, service.checkout):
            with self.assertRaises(ValueError):
                method(uuid4(), 10, 'year', 'u@example.org', 'https://example.org',
                       datetime.now(MOSCOW))
        provider.create_payment.assert_not_called()
        repo.save_order.assert_not_called()

    def test_repository_queries_always_bind_selected_store(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        repo = SubscriptionRepository(Mock(return_value=connection), payment_scope='live:1495040')
        repo.get_order(str(uuid4()), 10)
        repo.open_order_id(10)
        repo.payment_work(10)
        repo.onboarding_payment_results(10, datetime.now(MOSCOW))
        for call in cursor.execute.call_args_list:
            sql, params = call.args
            self.assertIn('payment_scope=%s', sql)
            self.assertIn('live:1495040', params)

    def test_new_order_saved_with_selected_scope(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (10,)
        repo = SubscriptionRepository(Mock(return_value=connection), payment_scope='live:1495040')
        repo.save_order(new_order(uuid4(), 10, 'month', 'u@example.org', datetime.now(MOSCOW)))
        sql, params = cursor.execute.call_args.args
        self.assertIn('payment_scope', sql)
        self.assertEqual(params[-1], 'live:1495040')
