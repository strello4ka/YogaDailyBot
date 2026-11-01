from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest

import httpx

from receipt_service.state import StateStore
from receipt_service.config import Settings
from receipt_service.providers import (MyNalogClient, PermanentFailure, UnknownWriteResult,
                                       YooKassaReader, parse_time)
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
    def send_alert(self, recipient, subject, body): self.sent.append((recipient, subject, body))


class ReceiptWorkerTest(unittest.TestCase):
    def test_overlap_never_moves_before_initial_receipt_cutoff(self):
        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            cutoff = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
            settings = SimpleNamespace(sync_from=cutoff, mynalog_writes_enabled=False,
                                       email_enabled=False)
            ranges = []
            reader = SimpleNamespace(successful_payments=lambda start, end:
                                     ranges.append((start, end)) or [])
            worker = ReceiptWorker(settings, store, reader, NalogStub(), MailStub())
            worker.run_once(cutoff + timedelta(minutes=5))
            worker.run_once(cutoff + timedelta(minutes=10))
            self.assertEqual([start for start, end in ranges], [cutoff, cutoff])
            self.assertEqual(parse_time(store.get_value('yookassa_sync_from')), cutoff)

    def test_malformed_actual_provider_response_recovers_on_next_cycle(self):
        posts = []

        def handler(request):
            if request.url.path.endswith('/auth/token'):
                return httpx.Response(200, json={'token': 'access'})
            if request.method == 'POST':
                posts.append(json.loads(request.content))
                return httpx.Response(200, content=b'invalid-json')
            return httpx.Response(200, json={'content': [{
                'name': posts[0]['services'][0]['name'], 'totalAmount': PAYMENT['amount']['value'],
                'approvedReceiptUuid': 'receipt-found'}]})

        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            client = MyNalogClient('refresh', 'device', transport=httpx.MockTransport(handler))
            settings = SimpleNamespace(sync_from=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                       mynalog_writes_enabled=True, email_enabled=True,
                                       mynalog_inn='123456789012')
            mail = MailStub()
            worker = ReceiptWorker(settings, store, YooKassaStub(), client, mail)
            worker.run_once(datetime(2026, 10, 28, 12, tzinfo=timezone.utc))
            self.assertEqual(store.job(PAYMENT['id'])['state'], 'unknown')
            worker.run_once(datetime(2026, 10, 28, 13, tzinfo=timezone.utc))
            self.assertEqual(store.job(PAYMENT['id'])['state'], 'emailed')
            self.assertEqual(len(posts), 1)
            self.assertEqual(len(mail.sent), 1)

    def test_pagination_failure_does_not_advance_checkpoint_or_duplicate_receipts(self):
        start = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
        fail = True

        def handler(request):
            if request.url.params.get('cursor'):
                if fail:
                    return httpx.Response(503)
                return httpx.Response(200, json={'items': []})
            return httpx.Response(200, json={'items': [PAYMENT], 'next_cursor': 'page2'})

        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            store.set_value('yookassa_checkpoint', start.isoformat())
            settings = SimpleNamespace(sync_from=start, mynalog_writes_enabled=True,
                                       email_enabled=True, mynalog_inn='123456789012')
            reader = YooKassaReader('shop', 'key', transport=httpx.MockTransport(handler))
            nalog, mail = NalogStub(), MailStub()
            worker = ReceiptWorker(settings, store, reader, nalog, mail)
            with self.assertRaises(httpx.HTTPStatusError):
                worker.run_once(start + timedelta(minutes=5))
            self.assertEqual(store.get_value('yookassa_checkpoint'), start.isoformat())
            fail = False
            worker.run_once(start + timedelta(minutes=10))
            self.assertEqual(nalog.created, 1)
            self.assertEqual(len(mail.sent), 1)

    def test_late_payment_is_discovered_by_capture_time_and_processed_once(self):
        start = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
        captured = start + timedelta(minutes=30)
        payment = dict(PAYMENT, created_at=start.isoformat(), captured_at=captured.isoformat())
        moment = start

        def handler(request):
            params = request.url.params
            self.assertNotIn('created_at.gte', params)
            self.assertEqual(params['status'], 'succeeded')
            lower, upper = (parse_time(params[key]) for key in
                            ('captured_at.gte', 'captured_at.lte'))
            items = [payment] if moment >= captured and lower <= captured <= upper else []
            return httpx.Response(200, json={'items': items})

        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            nalog, mail = NalogStub(), MailStub()
            settings = SimpleNamespace(sync_from=start, mynalog_writes_enabled=True,
                                       email_enabled=True, mynalog_inn='123456789012')
            reader = YooKassaReader('shop', 'key', transport=httpx.MockTransport(handler))
            worker = ReceiptWorker(settings, store, reader, nalog, mail)
            for minutes in range(5, 46, 5):
                moment = start + timedelta(minutes=minutes)
                worker.run_once(moment)
            self.assertEqual(store.job(payment['id'])['state'], 'emailed')
            self.assertEqual(nalog.created, 1)
            self.assertEqual(len(mail.sent), 1)

    def test_restart_does_not_skip_saved_checkpoint_older_than_sync_default(self):
        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            checkpoint = datetime(2026, 10, 25, tzinfo=timezone.utc)
            store.set_value('yookassa_checkpoint', checkpoint.isoformat())
            settings = SimpleNamespace(sync_from=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                       mynalog_writes_enabled=False, email_enabled=False)
            ranges = []
            reader = SimpleNamespace(successful_payments=lambda start, end:
                                     ranges.append((start, end)) or [])
            ReceiptWorker(settings, store, reader, NalogStub(), MailStub()).run_once(
                datetime(2026, 10, 29, tzinfo=timezone.utc))
            self.assertEqual(ranges[0][0], checkpoint - timedelta(minutes=10))

    def test_unexpected_write_error_is_reconciled_without_restarting_or_reposting(self):
        class BrokenResponseNalog(UncertainNalogStub):
            def create_income(self, *args):
                self.created += 1
                raise ValueError('private response must not be persisted')

        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            nalog, mail = BrokenResponseNalog(), MailStub()
            settings = SimpleNamespace(sync_from=datetime(2026, 10, 28, tzinfo=timezone.utc),
                                       mynalog_writes_enabled=True, email_enabled=True,
                                       mynalog_inn='123456789012', admin_email='admin@example.com')
            worker = ReceiptWorker(settings, store, YooKassaStub(), nalog, mail)
            worker.run_once(datetime(2026, 10, 28, 12, tzinfo=timezone.utc))
            job = store.job(PAYMENT['id'])
            self.assertEqual(job['state'], 'unknown')
            self.assertNotIn('private', job['last_error'])
            self.assertIsNotNone(job['alert_sent_at'])
            worker.run_once(datetime(2026, 10, 28, 13, tzinfo=timezone.utc))
            self.assertEqual(nalog.created, 1)
            self.assertEqual(store.job(PAYMENT['id'])['state'], 'emailed')

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
                email_transport='smtp', apps_script_url='', apps_script_secret='',
                admin_email='',
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

    def test_problem_alert_is_sent_only_once(self):
        with TemporaryDirectory() as directory:
            store = StateStore(str(Path(directory) / 'state.db'))
            store.add_payment(PAYMENT)
            store.transition('payment-1', 'ready', 'manual_review', last_error='rejected')
            mail = MailStub()
            settings = SimpleNamespace(admin_email='owner@example.com')
            worker = ReceiptWorker(settings, store, YooKassaStub(), NalogStub(), mail)

            worker._send_problem_alerts()
            worker._send_problem_alerts()

            self.assertEqual(len(mail.sent), 1)
            self.assertIsNotNone(store.job('payment-1')['alert_sent_at'])


class MyNalogClientTest(unittest.TestCase):
    def test_malformed_success_is_unknown_not_a_retryable_write(self):
        for body in (b'not-json', b'[]', b'null', b'{}'):
            with self.subTest(body=body):
                def handler(request):
                    if request.url.path.endswith('/auth/token'):
                        return httpx.Response(200, json={'token': 'access'})
                    return httpx.Response(200, content=body)

                client = MyNalogClient('refresh', 'device',
                                       transport=httpx.MockTransport(handler))
                with self.assertRaises(UnknownWriteResult):
                    client.create_income('Услуга', '100.00',
                                         datetime(2026, 10, 28, tzinfo=timezone.utc))

    def test_receipt_uses_payment_type_accepted_by_my_nalog(self):
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path.endswith('/auth/token'):
                return httpx.Response(200, json={'token': 'access'})
            return httpx.Response(200, json={'approvedReceiptUuid': 'receipt-1'})

        client = MyNalogClient('refresh', 'device', transport=httpx.MockTransport(handler))
        client.create_income('Услуга', '100.00', datetime(2026, 10, 28, tzinfo=timezone.utc))

        payload = json.loads(requests[-1].content)
        self.assertEqual(payload['paymentType'], 'CASH')
        self.assertEqual(payload['operationTime'], '2026-10-28T03:00:00.000+03:00')
        self.assertRegex(payload['requestTime'],
                         r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+03:00$')

    def test_receipt_rejection_keeps_bounded_provider_message(self):
        def handler(request):
            if request.url.path.endswith('/auth/token'):
                return httpx.Response(200, json={'token': 'access'})
            return httpx.Response(400, json={'code': 'validation.failed',
                                             'message': 'Некорректная дата расчёта',
                                             'private': 'must not be copied'})

        client = MyNalogClient('refresh', 'device', transport=httpx.MockTransport(handler))
        with self.assertRaisesRegex(
                PermanentFailure,
                'validation.failed: Некорректная дата расчёта'):
            client.create_income('Услуга', '100.00',
                                 datetime(2026, 10, 28, tzinfo=timezone.utc))

    def test_read_refreshes_expired_access_token_once(self):
        calls = {'auth': 0, 'incomes': 0}

        def handler(request):
            if request.url.path.endswith('/auth/token'):
                calls['auth'] += 1
                return httpx.Response(200, json={'token': f'access-{calls["auth"]}'})
            calls['incomes'] += 1
            if calls['incomes'] == 1:
                return httpx.Response(401)
            return httpx.Response(200, json={'content': []})

        client = MyNalogClient('refresh', 'device', transport=httpx.MockTransport(handler))
        self.assertIsNone(client.find_income(
            'Услуга', '100.00', datetime(2026, 10, 28, tzinfo=timezone.utc)))
        self.assertEqual(calls, {'auth': 2, 'incomes': 2})


if __name__ == '__main__':
    unittest.main()
