"""YooKassa adapter with an explicit test/live store boundary.

Creating a live client does not enable checkout anywhere in the application.
Credentials and payment bodies are never logged.
"""

from datetime import timedelta
from urllib.parse import urlparse, parse_qsl, urlencode
from uuid import UUID

import httpx

from app.subscription.tariff import local_time


class YooKassaClient:
    def __init__(self, shop_id, secret_key, *, expected_test, transport=None):
        if not str(shop_id).isdigit() or not secret_key:
            raise ValueError('Shop credentials are required')
        if not isinstance(expected_test, bool):
            raise ValueError('Expected store mode must be explicit')
        self.shop_id = str(shop_id)
        self.expected_test = expected_test
        self.client = httpx.Client(
            base_url='https://api.yookassa.ru/v3/',
            auth=(self.shop_id, secret_key), timeout=15,
            follow_redirects=False, transport=transport,
        )

    def close(self):
        self.client.close()

    def _request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def verify_store(self):
        settings = self._request('GET', 'me')
        if (settings.get('test') is not self.expected_test
                or str(settings.get('account_id')) != self.shop_id):
            raise ValueError('Payment creation requires a verified matching store')

    def verify_test_store(self):
        """Keep the existing test-only application entry point strict."""
        if not self.expected_test:
            raise ValueError('This entry point requires a test store')
        self.verify_store()

    def create_payment(self, order, return_url, now):
        parsed = urlparse(return_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('An HTTPS return URL is required')
        # Provider idempotence lasts 24h. Never silently create a second payment
        # when a previous creation request has an unknown outcome beyond that window.
        age = local_time(now) - local_time(order.created_at)
        if age < timedelta(0) or age >= timedelta(hours=23):
            raise ValueError('Order requires reconciliation before another creation attempt')
        UUID(order.order_id)
        # Preserve ?test=1 and identify this order after the provider redirect,
        # including when the browser has lost its sessionStorage.
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                 if key != 'checkout_order']
        query.append(('checkout_order', order.order_id))
        return_url = parsed._replace(query=urlencode(query)).geturl()
        self.verify_store()
        payment = self._request('POST', 'payments', headers={'Idempotence-Key': order.order_id}, json={
            'amount': {'value': order.amount, 'currency': 'RUB'},
            'capture': True,
            'confirmation': {'type': 'redirect', 'return_url': return_url},
            'description': 'YogaDailyBot: {} дней'.format(order.duration_days),
            'metadata': {'order_id': order.order_id},
        })
        if payment.get('test') is not self.expected_test:
            raise ValueError('Payment came from a store in the wrong mode')
        return payment

    def get_payment(self, payment_id):
        # IDs cannot inject a path/query into the provider request.
        UUID(payment_id)
        return self._request('GET', 'payments/' + payment_id)


class YooKassaTestClient(YooKassaClient):
    def __init__(self, shop_id, secret_key, *, transport=None):
        super().__init__(shop_id, secret_key, expected_test=True, transport=transport)


class YooKassaLiveClient(YooKassaClient):
    def __init__(self, shop_id, secret_key, *, transport=None):
        super().__init__(shop_id, secret_key, expected_test=False, transport=transport)
