"""Payment-provider settings for isolated test and production runtimes."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PaymentSettings:
    shop_id: str
    secret: str = field(repr=False)
    live: bool

    @property
    def scope(self):
        if not self.shop_id:
            return None
        return '{}:{}'.format('live' if self.live else 'test', self.shop_id)

    def client(self):
        from .yookassa import YooKassaLiveClient, YooKassaTestClient
        return (YooKassaLiveClient if self.live else YooKassaTestClient)(
            self.shop_id, self.secret)


def payment_settings(environment):
    # Validate environment isolation even when this helper is called independently.
    from app.subscription.runtime import subscription_settings
    runtime = subscription_settings(environment)
    if runtime is None:
        raise ValueError('Subscription mode is disabled')
    mode = environment.get('SUBSCRIPTION_PAYMENT_MODE', 'test')
    if mode not in ('test', 'live'):
        raise ValueError('Payment mode must be test or live')
    live = mode == 'live'
    if runtime.production and not live:
        raise ValueError('Production subscriptions require a live store')
    prefix = 'SUBSCRIPTION_YOOKASSA_{}'.format('LIVE' if live else 'TEST')
    shop_id = environment.get(prefix + '_SHOP_ID', '')
    secret = environment.get(prefix + '_SECRET_KEY', '')
    if bool(shop_id) != bool(secret):
        raise ValueError('Both shop ID and secret key must be configured')
    if live and not shop_id:
        raise ValueError('Live shop credentials are required')
    return PaymentSettings(shop_id, secret, live)
