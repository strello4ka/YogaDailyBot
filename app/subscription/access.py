"""A single access decision for menus, old buttons and scheduled delivery."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from .demo import Trial
from .tariff import PaidPeriod, local_time


class AccessState(str, Enum):
    FREE = "free"
    TRIAL = "trial"
    TRIAL_PAID = "trial_paid"
    PAID = "paid"


class Feature(str, Enum):
    PRACTICE_OF_DAY = "practice_of_day"
    PROGRESS = "progress"
    HELP = "help"
    COMPLETION_REMINDER = "completion_reminder"
    SELECTION = "selection"
    FAVORITES = "favorites"
    SCHEDULE = "schedule"


@dataclass(frozen=True)
class Subscription:
    trial: Optional[Trial] = None
    paid: Optional[PaidPeriod] = None

    def state(self, now: datetime) -> AccessState:
        current = local_time(now)
        if self.paid and local_time(self.paid.starts_at) <= current < local_time(self.paid.ends_at):
            return AccessState.PAID
        if self.trial and self.trial.is_active(current):
            if self.paid and local_time(self.paid.ends_at) > current:
                return AccessState.TRIAL_PAID
            return AccessState.TRIAL
        return AccessState.FREE


def has_access(subscription: Subscription, feature: Feature, now: datetime) -> bool:
    feature = Feature(feature)  # Unknown features are errors, never implicit grants.
    if feature in (Feature.PRACTICE_OF_DAY, Feature.PROGRESS, Feature.HELP,
                   Feature.COMPLETION_REMINDER):
        return True
    return subscription.state(now) != AccessState.FREE


def repository_for(context, user_id):
    """Return the configured repository when this user passes the rollout allowlist."""
    data = getattr(context, "bot_data", None) or {}
    if "subscription_test_users" not in data:
        return None
    users = data["subscription_test_users"]
    if users is not None and user_id not in users:
        return None
    return data.get("subscription_repository")


def current_subscription(context, user_id):
    repository = repository_for(context, user_id)
    return repository.get(user_id) if repository is not None else None


def runtime_has_access(context, user_id, feature, now=None):
    state = current_subscription(context, user_id)
    return state is None or has_access(state, feature, now or datetime.now().astimezone())
