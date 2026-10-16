"""Server-side order values and verification of freshly fetched payments."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
import re
from typing import Optional
from uuid import UUID

from app.subscription.tariff import TARIFFS, local_time

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Order:
    order_id: str
    user_id: int
    tariff_code: str
    duration_days: int
    amount_kopecks: int
    email: str
    created_at: datetime
    provider_payment_id: Optional[str] = None

    @property
    def amount(self):
        return '{}.{:02d}'.format(*divmod(self.amount_kopecks, 100))


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError('Введите e-mail')
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise ValueError('Проверь адрес e-mail')
    return value


def new_order(order_id, user_id, tariff_code, email, now):
    """Amounts and duration never come from browser input."""
    tariff = TARIFFS[tariff_code]
    return Order(str(order_id), user_id, tariff.code, tariff.days,
                 tariff.amount_kopecks, normalize_email(email), local_time(now))


def verify_payment(order, payment, *, expected_test=True):
    """Only pass a response fetched from the authenticated provider API here.

    Browser redirects and webhook bodies are not payment confirmations.
    Unknown states fail closed. Pending authorization never grants access.
    """
    if payment.get('test') is not expected_test:
        raise ValueError('Payment came from a store in the wrong mode')
    if not order.provider_payment_id or payment.get('id') != order.provider_payment_id:
        raise ValueError('Payment does not belong to this order')
    if payment.get('metadata', {}).get('order_id') != order.order_id:
        raise ValueError('Wrong payment metadata')
    amount = payment.get('amount', {})
    try:
        value = Decimal(str(amount.get('value')))
    except InvalidOperation:
        raise ValueError('Invalid payment amount') from None
    if (not value.is_finite() or value != Decimal(order.amount)
            or amount.get('currency') != 'RUB'):
        raise ValueError('Wrong payment amount or currency')
    status = payment.get('status')
    if status not in ('pending', 'waiting_for_capture', 'succeeded', 'canceled'):
        raise ValueError('Unknown payment status')
    if status == 'succeeded' and payment.get('paid') is not True:
        raise ValueError('Successful payment is not paid')
    return status


class PaymentService:
    def __init__(self, repository, provider):
        if not isinstance(getattr(provider, 'expected_test', None), bool):
            raise ValueError('Payment provider must declare test or live mode')
        self.repository = repository
        self.provider = provider

    def _verify(self, order, payment):
        return verify_payment(order, payment,
                              expected_test=self.provider.expected_test)

    def checkout(self, order_id, user_id, tariff_code, email, return_url, now):
        """Serialize different browser tabs and return an unfinished order first."""
        with self.repository.payment_creation_lock(user_id):
            existing_id = self.repository.open_order_id(user_id)
            if existing_id and existing_id != str(order_id):
                return existing_id, None
            return str(order_id), self.create(order_id, user_id, tariff_code, email, return_url, now)

    def create(self, order_id, user_id, tariff_code, email, return_url, now):
        """A retry must reuse its UUID, including after an HTTP timeout."""
        order_id = str(UUID(str(order_id)))
        requested = new_order(order_id, user_id, tariff_code, email, now)
        order = self.repository.get_order(order_id, user_id)
        if order is None:
            self.repository.save_order(requested)
            order = requested
        elif (order.tariff_code, order.email) != (requested.tariff_code, requested.email):
            raise ValueError('An existing order cannot be changed; use a new order ID')
        if order.provider_payment_id:
            payment = self.provider.get_payment(order.provider_payment_id)
        else:
            payment = self.provider.create_payment(order, return_url, now)
            from dataclasses import replace
            payment_id = str(UUID(payment['id']))
            order = replace(order, provider_payment_id=payment_id)
            self._verify(order, payment)
            self.repository.attach_payment(order, payment_id, now)
        self._verify(order, payment)
        return payment

    def refresh(self, order_id, user_id, now):
        return self.refresh_details(order_id, user_id, now)['status']

    def refresh_details(self, order_id, user_id, now, return_url=None):
        order = self.repository.get_order(order_id, user_id)
        if order is None:
            raise LookupError('Order not found')
        if order.provider_payment_id is None:
            if return_url:
                # Recover a creation response lost in transit with the same key.
                with self.repository.payment_creation_lock(user_id):
                    self.create(order.order_id, user_id, order.tariff_code, order.email, return_url, now)
                order = self.repository.get_order(order_id, user_id)
            if order.provider_payment_id is None:
                return {'status': 'created', 'confirmation_url': None}
        payment = self.provider.get_payment(order.provider_payment_id)
        status = self._verify(order, payment)
        if status == 'succeeded':
            # The repository serializes grants and ignores duplicate confirmations.
            granted = self.repository.grant_order(order, now)
            if granted:
                try:
                    self.repository.signal_payment(user_id)
                except Exception:
                    # Access has committed. A failed wakeup must not turn a
                    # successful payment into an error; periodic work retries.
                    logger.warning('Payment wakeup failed; periodic delivery will retry')
        elif status == 'canceled':
            self.repository.cancel_order(order, now)
        confirmation = payment.get('confirmation') or {}
        return {'status': status, 'confirmation_url': confirmation.get('confirmation_url')
                if status == 'pending' else None}
