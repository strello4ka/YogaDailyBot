"""Tariffs and date calculations, independent of Telegram and storage."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import MappingProxyType
from typing import Optional
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")


def local_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An aware datetime is required")
    return value.astimezone(MOSCOW)


def midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=MOSCOW)


def last_access_date(end: datetime) -> date:
    """End timestamps are exclusive; the UI displays the last accessible day."""
    return (local_time(end) - timedelta(microseconds=1)).date()


@dataclass(frozen=True)
class Tariff:
    code: str
    title: str
    days: int
    amount_kopecks: int

    @property
    def amount(self) -> str:
        return "{}.{:02d}".format(*divmod(self.amount_kopecks, 100))


TARIFFS = MappingProxyType({
    "month": Tariff("month", "1 месяц", 30, 35000),
    "quarter": Tariff("quarter", "3 месяца", 90, 80000),
    "half_year": Tariff("half_year", "6 месяцев", 180, 140000),
    "year": Tariff("year", "1 год", 365, 250000),
})


@dataclass(frozen=True)
class PaidPeriod:
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self):
        if local_time(self.ends_at) <= local_time(self.starts_at):
            raise ValueError("The paid period must have positive duration")


def purchased_period(
    tariff_code: str,
    purchased_at: datetime,
    *,
    trial_ends_at: Optional[datetime] = None,
    paid_ends_at: Optional[datetime] = None,
) -> PaidPeriod:
    """Calculate a new purchase, without recording or authorizing a payment.

    Remaining trial/paid access is preserved. Access starts immediately when
    there is no remaining period; its Moscow date counts as paid day one.
    The exclusive end is always midnight after the last paid calendar day.
    """
    tariff = TARIFFS[tariff_code]
    start = max(local_time(value) for value in
                (purchased_at, trial_ends_at, paid_ends_at) if value is not None)
    return PaidPeriod(start, midnight(start.date() + timedelta(days=tariff.days)))
