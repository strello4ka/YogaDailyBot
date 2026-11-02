"""Accelerated old-user timeline for the isolated test bot only.

Delete this module and its explicit callers before enabling subscriptions in production.
The regular 30-day gift and 14-day offer dates live in ``rules.py`` and are untouched.
"""

from datetime import datetime, timedelta

from ..tariff import local_time
from .rules import GiftPeriod, OldUserOffer


FAST_GIFT_DURATION = timedelta(minutes=15)
FAST_SPECIAL_OFFER_DURATION = timedelta(minutes=15)
FAST_GIFT_THREE_DAY_AFTER = timedelta(minutes=10)
FAST_GIFT_LAST_DAY_AFTER = timedelta(minutes=14)
FAST_SPECIAL_SEVEN_DAY_AFTER = timedelta(minutes=20)
FAST_SPECIAL_THREE_DAY_AFTER = timedelta(minutes=25)
FAST_SPECIAL_LAST_DAY_AFTER = timedelta(minutes=29)


def start_fast_offer(now: datetime) -> OldUserOffer:
    start = local_time(now)
    gift_end = start + FAST_GIFT_DURATION
    return OldUserOffer(
        GiftPeriod(start, gift_end),
        gift_end + FAST_SPECIAL_OFFER_DURATION,
    )


def is_fast_offer(offer: OldUserOffer) -> bool:
    gift_duration = local_time(offer.gift.ends_at) - local_time(offer.gift.starts_at)
    special_duration = local_time(offer.offer_ends) - local_time(offer.gift.ends_at)
    return (gift_duration == FAST_GIFT_DURATION
            and special_duration == FAST_SPECIAL_OFFER_DURATION)


def notification_times(offer: OldUserOffer):
    start = local_time(offer.gift.starts_at)
    return (
        ("gift_three_days", start + FAST_GIFT_THREE_DAY_AFTER),
        ("gift_last_day", start + FAST_GIFT_LAST_DAY_AFTER),
        ("gift_expired", start + FAST_GIFT_DURATION),
        ("special_prices_seven_days", start + FAST_SPECIAL_SEVEN_DAY_AFTER),
        ("special_prices_three_days", start + FAST_SPECIAL_THREE_DAY_AFTER),
        ("special_prices_last_day", start + FAST_SPECIAL_LAST_DAY_AFTER),
    )
