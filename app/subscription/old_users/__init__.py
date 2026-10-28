"""Temporary subscription-launch scenario for users registered before launch.

The package is deliberately isolated so it can be disabled and archived after
the one-off transition. Importing it never enrolls users or sends messages.
"""

from .rules import GiftPeriod, OldUserOffer, launch_offer

__all__ = ["GiftPeriod", "OldUserOffer", "launch_offer"]
