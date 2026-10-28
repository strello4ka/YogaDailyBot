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
    base_price: int
    final_price: int
    special_offer_applied: bool
    offer_ends_at_order: Optional[datetime]
    email: str
    created_at: datetime
    provider_payment_id: Optional[str] = None

    @property
    def amount(self):
        return '{}.{:02d}'.format(*divmod(self.final_price, 100))


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError('Введите e-mail')
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise ValueError('Проверь адрес e-mail')
    return value


class PriceChanged(ValueError):
    pass


def new_order(order_id, user_id, tariff_code, email, now, *, price=None,
              offer_ends_at_order=None):
    """Amounts and duration never come from browser input."""
    tariff = TARIFFS[tariff_code]
    base_price = tariff.base_price if price is None else price.base_price
    final_price = tariff.base_price if price is None else price.final_price
    special = False if price is None else price.special_offer_applied
    return Order(str(order_id), user_id, tariff.code, tariff.days,
                 base_price, final_price, special, offer_ends_at_order,
                 normalize_email(email), local_time(now))


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
    def __init__(self, repository, provider, *, allowed_tariffs=None):
        if not isinstance(getattr(provider, 'expected_test', None), bool):
            raise ValueError('Payment provider must declare test or live mode')
        self.repository = repository
        self.provider = provider
        self.allowed_tariffs = frozenset(allowed_tariffs) if allowed_tariffs is not None else None

    def _verify(self, order, payment):
        return verify_payment(order, payment,
                              expected_test=self.provider.expected_test)

    def checkout(self, order_id, user_id, tariff_code, email, return_url, now,
                 expected_final_price=None):
        """Serialize different browser tabs and return an unfinished order first."""
        if self.allowed_tariffs is not None and tariff_code not in self.allowed_tariffs:
            raise ValueError('Tariff is not enabled for this payment run')
        with self.repository.payment_creation_lock(user_id):
            existing_id = self.repository.open_order_id(user_id)
            if existing_id and existing_id != str(order_id):
                return existing_id, None
            return str(order_id), self.create(order_id, user_id, tariff_code, email, return_url, now,
                                              expected_final_price=expected_final_price)

    def create(self, order_id, user_id, tariff_code, email, return_url, now,
               expected_final_price=None):
        """A retry must reuse its UUID, including after an HTTP timeout."""
        if self.allowed_tariffs is not None and tariff_code not in self.allowed_tariffs:
            raise ValueError('Tariff is not enabled for this payment run')
        order_id = str(UUID(str(order_id)))
        order = self.repository.get_order(order_id, user_id)
        if order is None:
            price, offer_ends = self.repository.checkout_price(user_id, tariff_code, now)
            if expected_final_price is not None and int(expected_final_price) != price.final_price:
                raise PriceChanged('Цена изменилась. Проверь актуальные тарифы.')
            requested = new_order(order_id, user_id, tariff_code, email, now, price=price,
                                  offer_ends_at_order=offer_ends)
            self.repository.save_order(requested)
            order = requested
        elif (order.tariff_code, order.email) != (tariff_code, normalize_email(email)):
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
            self.repository.grant_order(order, now)
        elif status == 'canceled':
            self.repository.cancel_order(order, now)
        if status in ('succeeded', 'canceled'):
            try:
                # One wakeup per verified terminal result, regardless of source.
                # Repeated checks can retry delivery; grants and notices remain
                # idempotent, and the delivery worker never re-polls the provider.
                self.repository.signal_payment(user_id)
            except Exception:
                logger.warning('Payment wakeup failed; periodic delivery will retry')
        confirmation = payment.get('confirmation') or {}
        return {'status': status, 'confirmation_url': confirmation.get('confirmation_url')
                if status == 'pending' else None}
