"""Special prices that exist only for the subscription-launch transition."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional

from ..tariff import TARIFFS
from .rules import OldUserOffer

SPECIAL_PRICES = MappingProxyType({
    "month": 25000,
    "quarter": 60000,
    "half_year": 100000,
    "year": 180000,
})


@dataclass(frozen=True)
class CheckoutPrice:
    base_price: int
    final_price: int
    special_offer_applied: bool = False


def checkout_price(tariff_code: str, offer: Optional[OldUserOffer], now) -> CheckoutPrice:
    base = TARIFFS[tariff_code].base_price
    if offer is not None and offer.special_price_active(now):
        return CheckoutPrice(base, SPECIAL_PRICES[tariff_code], True)
    return CheckoutPrice(base, base)
