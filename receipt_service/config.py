from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os


def _required(name):
    value = os.getenv(name, '').strip()
    if not value:
        raise ValueError(f'{name} is required')
    return value


def _boolean(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {'true', 'false'}:
        raise ValueError(f'{name} must be true or false')
    return value.lower() == 'true'


@dataclass(frozen=True)
class Settings:
    yookassa_shop_id: str
    yookassa_secret_key: str
    mynalog_refresh_token: str
    mynalog_device_id: str
    mynalog_inn: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    state_path: str
    poll_seconds: int
    sync_from: datetime
    mynalog_writes_enabled: bool
    mynalog_auth_check_on_start: bool
    email_enabled: bool
    backfill_payment_id: str
    backfill_email: str
    backfill_service_name: str

    @classmethod
    def from_env(cls):
        writes_enabled = _boolean('MYNALOG_WRITES_ENABLED')
        email_enabled = _boolean('RECEIPT_EMAIL_ENABLED')
        start = os.getenv('RECEIPT_SYNC_FROM', '').strip()
        sync_from = (datetime.fromisoformat(start.replace('Z', '+00:00')) if start
                     else datetime.now(timezone.utc) - timedelta(hours=24))
        if sync_from.tzinfo is None:
            raise ValueError('RECEIPT_SYNC_FROM must contain a timezone')
        return cls(
            yookassa_shop_id=_required('YOOKASSA_SHOP_ID'),
            yookassa_secret_key=_required('YOOKASSA_SECRET_KEY'),
            mynalog_refresh_token=(_required('MYNALOG_REFRESH_TOKEN') if writes_enabled else
                                   os.getenv('MYNALOG_REFRESH_TOKEN', '').strip()),
            mynalog_device_id=(_required('MYNALOG_DEVICE_ID') if writes_enabled else
                               os.getenv('MYNALOG_DEVICE_ID', '').strip()),
            mynalog_inn=(_required('MYNALOG_INN') if email_enabled else
                         os.getenv('MYNALOG_INN', '').strip()),
            smtp_host=(_required('RECEIPT_SMTP_HOST') if email_enabled else
                       os.getenv('RECEIPT_SMTP_HOST', '').strip()),
            smtp_port=int(os.getenv('RECEIPT_SMTP_PORT', '465')),
            smtp_user=(_required('RECEIPT_SMTP_USER') if email_enabled else
                       os.getenv('RECEIPT_SMTP_USER', '').strip()),
            smtp_password=(_required('RECEIPT_SMTP_PASSWORD') if email_enabled else
                           os.getenv('RECEIPT_SMTP_PASSWORD', '').strip()),
            smtp_from=(os.getenv('RECEIPT_SMTP_FROM', '').strip()
                       or os.getenv('RECEIPT_SMTP_USER', '').strip()),
            state_path=os.getenv('RECEIPT_STATE_PATH', '/data/receipts.sqlite3'),
            poll_seconds=max(30, int(os.getenv('RECEIPT_POLL_SECONDS', '300'))),
            sync_from=sync_from.astimezone(timezone.utc),
            mynalog_writes_enabled=writes_enabled,
            mynalog_auth_check_on_start=_boolean('MYNALOG_AUTH_CHECK_ON_START'),
            email_enabled=email_enabled,
            backfill_payment_id=os.getenv('RECEIPT_BACKFILL_PAYMENT_ID', '').strip(),
            backfill_email=os.getenv('RECEIPT_BACKFILL_EMAIL', '').strip(),
            backfill_service_name=os.getenv('RECEIPT_BACKFILL_SERVICE_NAME', '').strip(),
        )
