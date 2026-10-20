"""Notifications are wakeups, not proof of payment. No Telegram session needed."""
from uuid import UUID


def handle_notification(data, service, now, allowed_users=None):
    if data.get('type') != 'notification' or not isinstance(data.get('event'), str):
        raise ValueError('Invalid notification')
    if data['event'] not in ('payment.succeeded', 'payment.canceled'):
        return 'ignored'
    obj = data.get('object')
    if not isinstance(obj, dict):
        raise ValueError('Invalid payment object')
    payment_id = str(UUID(obj.get('id', '')))
    metadata = obj.get('metadata') or {}
    if not isinstance(metadata, dict):
        raise ValueError('Invalid metadata')
    hint = metadata.get('order_id')
    hint = str(UUID(hint)) if hint else None
    order = service.repository.webhook_order(payment_id, hint)
    if order is None:
        # Other shop/runtime orders must never be verified or granted here.
        return 'ignored'
    if allowed_users is not None and order.user_id not in allowed_users:
        return 'ignored'
    if order.provider_payment_id is None:
        # Notification can race the create-payment response being persisted.
        # Ask YooKassa to retry; never create a payment from a notification.
        raise RuntimeError('Payment attachment not committed yet')
    if str(order.provider_payment_id) != payment_id:
        raise ValueError('Payment mismatch')
    # This fetches the payment using our shop credentials and verifies mode,
    # payment ID, order metadata, server-side amount/currency and paid status.
    result = service.refresh_details(order.order_id, order.user_id, now)
    if result['status'] not in ('succeeded', 'canceled'):
        raise RuntimeError('Terminal payment status not available yet')
    return result['status']
