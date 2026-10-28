"""Date and eligibility rules for the one-off old-users transition."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ..tariff import local_time, midnight

GIFT_DAYS = 30
EXTRA_OFFER_DAYS = 14


@dataclass(frozen=True)
class GiftPeriod:
    starts_at: datetime
    ends_at: datetime

    def is_active(self, now: datetime) -> bool:
        current = local_time(now)
        return local_time(self.starts_at) <= current < local_time(self.ends_at)


@dataclass(frozen=True)
class OldUserOffer:
    gift: GiftPeriod
    offer_ends: datetime
    used_at: Optional[datetime] = None

    def special_price_active(self, now: datetime) -> bool:
        current = local_time(now)
        return (self.used_at is None
                and local_time(self.gift.starts_at) <= current < local_time(self.offer_ends))


def launch_offer(launch_at: datetime) -> OldUserOffer:
    """Build fixed Moscow calendar boundaries from the approved launch moment."""
    start = local_time(launch_at)
    gift_end = midnight(start.date() + timedelta(days=GIFT_DAYS))
    return OldUserOffer(GiftPeriod(start, gift_end),
                        midnight(gift_end.date() + timedelta(days=EXTRA_OFFER_DAYS)))
