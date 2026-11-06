"""Fail-closed subscription runtime configuration for test and production."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SubscriptionSettings:
    runtime: str
    database_name: str
    miniapp_url: str
    allowed_users: object = None

    @property
    def production(self) -> bool:
        return self.runtime == "production"


def _enabled(environment, name):
    value = environment.get(name, "").strip().lower()
    if value not in ("", "true", "false"):
        raise ValueError("{} must be true or false".format(name))
    return value == "true"


def _bot_token(environment):
    bot_id, separator, token_secret = environment.get("BOT_TOKEN", "").partition(":")
    if not separator or not bot_id.isdigit() or not token_secret:
        raise ValueError("BOT_TOKEN must contain a numeric bot ID and token secret")


def _https_url(value):
    if not value:
        return
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Mini App requires a public HTTPS URL without credentials")


def subscription_settings(environment):
    """Return one explicit runtime or None when subscriptions are disabled."""
    test = _enabled(environment, "SUBSCRIPTION_TEST_ENABLED")
    production = _enabled(environment, "SUBSCRIPTION_ENABLED")
    if test and production:
        raise ValueError("Test and production subscription runtimes are mutually exclusive")
    if not test and not production:
        return None
    _bot_token(environment)
    miniapp_url = environment.get("SUBSCRIPTION_MINIAPP_URL", "").strip()
    _https_url(miniapp_url)

    if test:
        test_env = Path(__file__).resolve().parents[2] / "test" / ".env.test"
        if Path(environment.get("ENV_FILE", "")).resolve() != test_env:
            raise ValueError("Test subscriptions require the project's test/.env.test")
        database_name = environment.get("SUBSCRIPTION_TEST_DATABASE", "").strip()
        if database_name != "yogadaily_test":
            raise ValueError("Test subscriptions require the isolated yogadaily_test database")
        raw_users = environment.get("SUBSCRIPTION_TEST_USERS", "").strip()
        users = (frozenset(int(value.strip()) for value in raw_users.split(",") if value.strip())
                 if raw_users else None)
        if users is not None and (not users or any(user_id <= 0 for user_id in users)):
            raise ValueError("Test user IDs must be positive")
        return SubscriptionSettings("test", database_name, miniapp_url, users)

    if environment.get("RAILWAY_ENVIRONMENT_NAME", "").strip() != "production":
        raise ValueError("Production subscriptions require Railway production environment")
    if Path(environment.get("ENV_FILE", ".env")).name == ".env.test":
        raise ValueError("Production subscriptions cannot use the test env file")
    database_name = environment.get("SUBSCRIPTION_DATABASE", "").strip()
    if not database_name or database_name == "yogadaily_test":
        raise ValueError("Production subscription database must be explicit and non-test")
    if not miniapp_url:
        raise ValueError("Production subscriptions require SUBSCRIPTION_MINIAPP_URL")
    if not _enabled(environment, "SUBSCRIPTION_ONBOARDING_ENABLED"):
        raise ValueError("Production subscriptions require the subscription onboarding step")
    if environment.get("SUBSCRIPTION_PAYMENT_MODE", "").strip() != "live":
        raise ValueError("Production subscriptions require the live YooKassa mode")
    return SubscriptionSettings("production", database_name, miniapp_url, None)
