from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from receipt_service.state import StateStore
from receipt_service.config import Settings
from receipt_service.providers import UnknownWriteResult
from receipt_service.worker import ReceiptWorker
from receipt_service.main import run_backfill


PAYMENT = {'id': 'payment-1', 'status': 'succeeded', 'paid': True, 'test': False,
           'captured_at': '2026-10-28T10:00:00Z',
           'amount': {'value': '499.00', 'currency': 'RUB'},
           'metadata': {'order_id': 'order-1', 'receipt_service': 'yoga_daily_v1',
                        'customer_email': 'buyer@example.com',
                        'service_name': 'Доступ на 30 дней'}}


class YooKassaStub:
    def successful_payments(self, start, end):
        yield PAYMENT


class NalogStub:
    def __init__(self): self.created = 0
    def create_income(self, name, amount, paid_at):
        self.created += 1
        return 'receipt-1'
    def find_income(self, name, amount, paid_at): return None


class UncertainNalogStub(NalogStub):
    def create_income(self, name, amount, paid_at):
        self.created += 1
        raise UnknownWriteResult('response lost')

    def find_income(self, name, amount, paid_at):
        return 'receipt-found'


class MailStub:
    def __init__(self): self.sent = []
    def send(self, recipient, url): self.sent.append((recipient, url))


class ReceiptWorkerTest(unittest.TestCase):
    def test_registers_once_emails_and_removes_address(self):
        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            nalog, mail = NalogStub(), MailStub()
            settings = SimpleNamespace(sync_from=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                       mynalog_writes_enabled=True, email_enabled=True,
                                       mynalog_inn='123456789012')
            worker = ReceiptWorker(settings, store, YooKassaStub(), nalog, mail)
            worker.run_once(datetime(2026, 10, 28, 12, tzinfo=timezone.utc))
            worker.run_once(datetime(2026, 10, 28, 13, tzinfo=timezone.utc))
            self.assertEqual(nalog.created, 1)
            self.assertEqual(len(mail.sent), 1)
            job = store.jobs('emailed')[0]
            self.assertIsNone(job['customer_email'])

    def test_write_flag_keeps_job_ready(self):
        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            nalog = NalogStub()
            settings = SimpleNamespace(sync_from=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                       mynalog_writes_enabled=False, email_enabled=False,
                                       mynalog_inn='123456789012')
            ReceiptWorker(settings, store, YooKassaStub(), nalog, MailStub()).run_once(
                datetime(2026, 10, 28, 12, tzinfo=timezone.utc))
            self.assertEqual(nalog.created, 0)
            self.assertEqual(len(store.jobs('ready')), 1)

    def test_lost_write_response_is_reconciled_without_second_post(self):
        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            nalog = UncertainNalogStub()
            settings = SimpleNamespace(sync_from=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                       mynalog_writes_enabled=True, email_enabled=False,
                                       mynalog_inn='123456789012')
            worker = ReceiptWorker(settings, store, YooKassaStub(), nalog, MailStub())
            worker.run_once(datetime(2026, 10, 28, 12, tzinfo=timezone.utc))
            self.assertEqual(len(store.jobs('unknown')), 1)
            worker.run_once(datetime(2026, 10, 28, 13, tzinfo=timezone.utc))
            self.assertEqual(nalog.created, 1)
            self.assertEqual(store.jobs('registered')[0]['receipt_uuid'], 'receipt-found')

    def test_crash_during_write_is_reconciled_not_reposted(self):
        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            store.add_payment(PAYMENT)
            self.assertTrue(store.transition('payment-1', 'ready', 'creating'))
            self.assertEqual(store.recover_interrupted_writes(), 1)
            self.assertEqual(len(store.jobs('unknown')), 1)
            self.assertEqual(len(store.jobs('ready')), 0)

    def test_backfill_registers_and_emails_once_while_automatic_flags_are_off(self):
        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            nalog, mail = NalogStub(), MailStub()
            yookassa = YooKassaStub()
            yookassa.successful_payment = lambda payment_id: dict(PAYMENT)
            settings = Settings(
                yookassa_shop_id='1', yookassa_secret_key='secret',
                sync_from=datetime(2026, 10, 28, tzinfo=timezone.utc),
                mynalog_writes_enabled=False, email_enabled=False,
                mynalog_refresh_token='refresh', mynalog_device_id='device',
                mynalog_inn='123456789012', smtp_host='smtp.example.com', smtp_port=465,
                smtp_user='sender', smtp_password='password', smtp_from='sender@example.com',
                state_path=str(Path(directory) / 'state.db'), poll_seconds=300,
                mynalog_auth_check_on_start=False,
                backfill_payment_id='payment-1', backfill_email='buyer@example.com',
                backfill_service_name='Доступ на 30 дней')
            worker = ReceiptWorker(settings, store, yookassa, nalog, mail)

            run_backfill(worker, settings)
            run_backfill(worker, settings)

            self.assertEqual(nalog.created, 1)
            self.assertEqual(len(mail.sent), 1)
            self.assertEqual(store.job('payment-1')['state'], 'emailed')


if __name__ == '__main__':
    unittest.main()
