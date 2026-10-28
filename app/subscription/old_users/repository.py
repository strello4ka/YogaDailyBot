"""SQL helpers and checkout view owned by the temporary scenario."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..tariff import local_time
from .rules import GiftPeriod, OldUserOffer, launch_offer


@dataclass(frozen=True)
class CheckoutProfile:
    email: Optional[str]
    trial_ends: Optional[datetime]
    subscription_ends: Optional[datetime]
    old_user_offer: Optional[OldUserOffer]


def offer_from_values(gift_starts, gift_ends, offer_ends, used_at):
    if gift_starts is None:
        return None
    return OldUserOffer(GiftPeriod(gift_starts, gift_ends), offer_ends, used_at)


def enroll(cursor, launch_at: datetime) -> int:
    """Freeze the cohort once; caller owns transaction and explicit approval."""
    offer = launch_offer(launch_at)
    cursor.execute(
        "SELECT gift_starts,gift_ends,offer_ends FROM subscription_accounts "
        "WHERE is_old_user IS TRUE LIMIT 1"
    )
    frozen = cursor.fetchone()
    if frozen is not None:
        expected = (offer.gift.starts_at, offer.gift.ends_at, offer.offer_ends)
        if tuple(frozen) != expected:
            raise ValueError("Old-user cohort is already frozen for another launch date")
        return 0
    launch_day = local_time(launch_at).date()
    cursor.execute(
        "INSERT INTO subscription_accounts "
        "(user_id,is_old_user,gift_starts,gift_ends,offer_ends,subscription_state,updated_at) "
        "SELECT user_id,TRUE,%s,%s,%s,'gift',%s FROM users WHERE created_at::date < %s "
        "ON CONFLICT (user_id) DO UPDATE SET is_old_user=TRUE,gift_starts=%s,gift_ends=%s,"
        "offer_ends=%s,subscription_state=CASE "
        "WHEN subscription_accounts.subscription_starts<=%s "
        "AND subscription_accounts.subscription_ends>%s THEN 'paid' "
        "WHEN subscription_accounts.subscription_ends>%s THEN 'gift_paid' "
        "ELSE 'gift' END,updated_at=%s "
        "WHERE subscription_accounts.is_old_user IS FALSE",
        (offer.gift.starts_at, offer.gift.ends_at, offer.offer_ends, launch_at, launch_day,
         offer.gift.starts_at, offer.gift.ends_at, offer.offer_ends,
         launch_at, launch_at, launch_at, launch_at),
    )
    return cursor.rowcount
