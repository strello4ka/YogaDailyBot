from datetime import datetime, timedelta, timezone
from decimal import Decimal
import httpx
from zoneinfo import ZoneInfo


class UnknownWriteResult(RuntimeError):
    """The request may have reached My Nalog; never blindly repeat it."""


class TemporaryFailure(RuntimeError):
    pass


class PermanentFailure(RuntimeError):
    pass


class YooKassaReader:
    def __init__(self, shop_id, secret_key, transport=None):
        self.client = httpx.Client(base_url='https://api.yookassa.ru/v3/',
                                   auth=(shop_id, secret_key), timeout=30,
                                   transport=transport)

    def successful_payments(self, created_from, created_to):
        params = {'created_at.gte': created_from.isoformat().replace('+00:00', 'Z'),
                  'created_at.lte': created_to.isoformat().replace('+00:00', 'Z'), 'limit': 100}
        while True:
            response = self.client.get('payments', params=params)
            response.raise_for_status()
            data = response.json()
            for payment in data.get('items', []):
                metadata = payment.get('metadata') or {}
                if (payment.get('status') == 'succeeded' and payment.get('paid') is True
                        and payment.get('test') is False
                        and metadata.get('receipt_service') == 'yoga_daily_v1'):
                    required = ('order_id', 'customer_email', 'service_name')
                    if all(metadata.get(key) for key in required):
                        yield payment
            cursor = data.get('next_cursor')
            if not cursor:
                return
            params['cursor'] = cursor

    def successful_payment(self, payment_id):
        response = self.client.get('payments/' + payment_id)
        response.raise_for_status()
        payment = response.json()
        if (payment.get('status') != 'succeeded' or payment.get('paid') is not True
                or payment.get('test') is not False or not payment.get('captured_at')):
            raise PermanentFailure('Backfill payment is not a captured live payment')
        return payment


class MyNalogClient:
    base_url = 'https://lknpd.nalog.ru/api/v1/'
    timezone = ZoneInfo('Europe/Moscow')

    def __init__(self, refresh_token, device_id, *, on_refresh_token=None, transport=None):
        self.refresh_token = refresh_token
        self.device_id = device_id
        self.on_refresh_token = on_refresh_token
        self.token = None
        self.client = httpx.Client(base_url=self.base_url, timeout=30, transport=transport,
                                   headers={'Origin': 'https://lknpd.nalog.ru',
                                            'Referer': 'https://lknpd.nalog.ru/'})

    def authenticate(self):
        response = self.client.post('auth/token', json={'refreshToken': self.refresh_token,
            'deviceInfo': {'sourceDeviceId': self.device_id, 'sourceType': 'WEB',
                           'appVersion': '1.0.0', 'metaDetails': {}}})
        self._check_read(response)
        data = response.json()
        self.token = data.get('token')
        if not self.token:
            raise TemporaryFailure('My Nalog auth response has no token')
        refreshed = data.get('refreshToken')
        if refreshed and refreshed != self.refresh_token:
            self.refresh_token = refreshed
            if self.on_refresh_token:
                self.on_refresh_token(refreshed)

    @property
    def headers(self):
        if not self.token:
            self.authenticate()
        return {'Authorization': f'Bearer {self.token}'}

    def create_income(self, name, amount, operation_time):
        amount = str(Decimal(amount).quantize(Decimal('0.01')))
        payload = {'operationTime': self._format_time(operation_time),
                   'requestTime': self._format_time(datetime.now(timezone.utc)),
                   'services': [{'name': name, 'amount': amount, 'quantity': 1}],
                   'totalAmount': amount,
                   'client': {'contactPhone': None, 'displayName': None, 'inn': None,
                              'incomeType': 'FROM_INDIVIDUAL'},
                   # This is the value accepted by the current My Nalog web API.
                   # `ACCOUNT` looks semantically appropriate for YooKassa, but the
                   # API rejects it as an invalid request format.
                   'paymentType': 'CASH', 'ignoreMaxTotalIncomeRestriction': False}
        try:
            response = self.client.post('income', json=payload, headers=self.headers)
        except (httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError) as error:
            raise UnknownWriteResult('My Nalog write response was lost') from error
        except (httpx.ConnectTimeout, httpx.ConnectError) as error:
            raise TemporaryFailure('Cannot connect to My Nalog') from error
        if response.status_code == 401:
            self.token = None
            raise TemporaryFailure('My Nalog token expired')
        if response.status_code >= 500 or response.status_code == 408:
            raise UnknownWriteResult(f'My Nalog returned HTTP {response.status_code}')
        if response.status_code == 429:
            raise TemporaryFailure('My Nalog rate limit')
        if response.status_code >= 400:
            detail = self._error_detail(response)
            suffix = f' ({detail})' if detail else ''
            raise PermanentFailure(
                f'My Nalog rejected receipt: HTTP {response.status_code}{suffix}')
        receipt_uuid = response.json().get('approvedReceiptUuid')
        if not receipt_uuid:
            raise UnknownWriteResult('My Nalog response has no receipt UUID')
        return receipt_uuid

    @classmethod
    def _format_time(cls, value):
        """Match the millisecond, explicit-offset format used by the web client."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('My Nalog timestamps must contain a timezone')
        return value.astimezone(cls.timezone).isoformat(timespec='milliseconds')

    @staticmethod
    def _error_detail(response):
        """Keep only bounded provider diagnostics; never copy arbitrary response bodies."""
        try:
            data = response.json()
        except (ValueError, TypeError):
            return ''
        if not isinstance(data, dict):
            return ''
        parts = []
        for key in ('code', 'message'):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip()[:160])
        return ': '.join(parts)[:240]

    def find_income(self, name, amount, operation_time):
        expected = Decimal(amount)
        params = {'from': (operation_time - timedelta(days=1)).isoformat(timespec='milliseconds'),
                  'to': (operation_time + timedelta(days=1)).isoformat(timespec='milliseconds'),
                  'offset': 0, 'sortBy': 'operation_time:desc', 'limit': 50}
        for _ in range(100):
            response = self._authenticated_get('incomes', params=params)
            incomes = response.json().get('content', [])
            for income in incomes:
                if (not income.get('cancellationInfo') and income.get('name') == name
                        and Decimal(str(income.get('totalAmount'))) == expected):
                    return income.get('approvedReceiptUuid')
            if len(incomes) < params['limit']:
                return None
            params['offset'] += params['limit']
        raise TemporaryFailure('Too many My Nalog receipt pages')

    def _authenticated_get(self, path, **kwargs):
        """Retry one read after refreshing an expired access token."""
        response = self.client.get(path, headers=self.headers, **kwargs)
        if response.status_code == 401:
            self.token = None
            response = self.client.get(path, headers=self.headers, **kwargs)
        self._check_read(response)
        return response

    @staticmethod
    def _check_read(response):
        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            raise TemporaryFailure(f'My Nalog temporarily unavailable: HTTP {response.status_code}')
        if response.status_code >= 400:
            raise PermanentFailure(f'My Nalog request rejected: HTTP {response.status_code}')


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
