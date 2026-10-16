"""One-off trial period, counting the Moscow launch date as day one."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .tariff import local_time, midnight

TRIAL_DAYS = 14
FAST_TRIAL_DURATION = timedelta(minutes=15)
FAST_THREE_DAY_NOTICE_AFTER = timedelta(minutes=10)
FAST_LAST_DAY_NOTICE_AFTER = timedelta(minutes=14)
FAST_FOLLOWUP_AFTER = timedelta(minutes=17)


@dataclass(frozen=True)
class Trial:
    started_at: datetime
    ends_at: datetime

    def __post_init__(self):
        if local_time(self.ends_at) <= local_time(self.started_at):
            raise ValueError("The trial must have positive duration")

    def is_active(self, now: datetime) -> bool:
        return local_time(self.started_at) <= local_time(now) < local_time(self.ends_at)

    def days_left(self, now: datetime) -> int:
        if not self.is_active(now):
            return 0
        return (local_time(self.ends_at).date() - local_time(now).date()).days


def start_trial(now: datetime, existing: Optional[Trial] = None) -> Trial:
    """Existing trial is immutable, including after expiry and repeated /start.

    Storage must enforce one trial per user atomically; this function has no IO.
    """
    if existing is not None:
        return existing
    start = local_time(now)
    return Trial(start, midnight(start.date() + timedelta(days=TRIAL_DAYS)))


def is_fast_trial(trial: Optional[Trial]) -> bool:
    """Recognize the explicit short trial used only by the isolated test bot."""
    return bool(trial and local_time(trial.ends_at) - local_time(trial.started_at)
                == FAST_TRIAL_DURATION)
