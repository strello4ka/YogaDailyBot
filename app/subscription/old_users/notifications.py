"""Pure notification dates for the temporary scenario; no sending on import."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..tariff import local_time
from .rules import OldUserOffer


@dataclass(frozen=True)
class OldUserNotification:
    kind: str
    scheduled_at: datetime


def notification_schedule(offer: OldUserOffer):
    gift_end = local_time(offer.gift.ends_at)
    offer_end = local_time(offer.offer_ends)
    return (
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
