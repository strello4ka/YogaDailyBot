"""Pure notification dates for the temporary scenario; no sending on import."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..tariff import local_time
from .rules import OldUserOffer

NOTIFICATION_KINDS = frozenset((
    'launch', 'launch_feedback',
    'gift_three_days', 'gift_last_day', 'gift_expired',
    'special_prices_seven_days', 'special_prices_three_days', 'special_prices_last_day',
))


@dataclass(frozen=True)
class OldUserNotification:
    kind: str
    scheduled_at: datetime


def notification_schedule(offer: OldUserOffer):
    gift_end = local_time(offer.gift.ends_at)
    offer_end = local_time(offer.offer_ends)
    return (
        OldUserNotification("launch", local_time(offer.gift.starts_at)),
        OldUserNotification("launch_feedback",
                            local_time(offer.gift.starts_at) + timedelta(hours=2)),
        OldUserNotification("gift_three_days",
                            gift_end - timedelta(days=3) + timedelta(hours=13)),
        OldUserNotification("gift_last_day",
                            gift_end - timedelta(days=1) + timedelta(hours=19)),
        OldUserNotification("gift_expired", gift_end + timedelta(hours=8)),
        OldUserNotification("special_prices_seven_days",
                            offer_end - timedelta(days=7) + timedelta(hours=19)),
        OldUserNotification("special_prices_three_days",
                            offer_end - timedelta(days=3) + timedelta(hours=19)),
        OldUserNotification("special_prices_last_day",
                            offer_end - timedelta(days=1) + timedelta(hours=19)),
    )


def due_notifications(offer, now, *, gift_active, free, has_paid, payment_pending):
    """Today's reminders only; never replay obsolete marketing after downtime."""
    now = local_time(now)
    result = []
    for event in notification_schedule(offer):
        scheduled = local_time(event.scheduled_at)
        if scheduled.date() != now.date() or scheduled > now:
            continue
        if event.kind in ('launch', 'launch_feedback'):
            eligible = offer.gift.is_active(now)
        elif has_paid:
            eligible = False
        elif event.kind == 'gift_expired':
            eligible = free  # Access expires even while checkout is pending.
        elif event.kind.startswith('gift_'):
            eligible = gift_active and not payment_pending
        else:
            eligible = offer.special_price_active(now) and not payment_pending
        if eligible:
            result.append(event)
    return result
