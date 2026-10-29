from datetime import datetime, timedelta, timezone
import logging
import time

from receipt_service.providers import (PermanentFailure, TemporaryFailure,
                                       UnknownWriteResult, parse_time)


logger = logging.getLogger(__name__)


class ReceiptWorker:
    def __init__(self, settings, store, yookassa, mynalog, mailer):
        self.settings, self.store = settings, store
        self.yookassa, self.mynalog, self.mailer = yookassa, mynalog, mailer

    def run_once(self, now=None):
        now = now or datetime.now(timezone.utc)
        checkpoint = self.store.get_value('yookassa_checkpoint')
        start = parse_time(checkpoint) if checkpoint else self.settings.sync_from
        # Re-read a small overlap; payment_id uniqueness makes this safe.
        start = max(self.settings.sync_from, start - timedelta(minutes=10))
        discovered = 0
        for payment in self.yookassa.successful_payments(start, now):
            self.store.add_payment(payment)
            discovered += 1
        self.store.set_value('yookassa_checkpoint', now.isoformat())

        for job in self.store.jobs('unknown'):
            self._reconcile(job)
        for job in self.store.jobs('ready'):
            self._register(job)
        for job in self.store.jobs('registered', 'email_pending'):
            self._email(job)
        self._send_problem_alerts()
        counts = self.store.counts()
        logger.info('Receipt cycle complete: discovered=%s states=%s', discovered, counts)
        return {'discovered': discovered, 'states': counts}

    def _receipt_name(self, job):
        return '{} [yookassa:{}]'.format(job['service_name'], job['payment_id'])

    def _register(self, job):
        if not self.settings.mynalog_writes_enabled:
            return
        if not self.store.transition(job['payment_id'], 'ready', 'creating'):
            return
        try:
            uuid = self.mynalog.create_income(self._receipt_name(job), job['amount'],
                                               parse_time(job['paid_at']))
        except UnknownWriteResult as error:
            self.store.transition(job['payment_id'], 'creating', 'unknown', last_error=str(error))
        except TemporaryFailure as error:
            self.store.transition(job['payment_id'], 'creating', 'ready', last_error=str(error))
        except PermanentFailure as error:
            self.store.transition(job['payment_id'], 'creating', 'manual_review', last_error=str(error))
        else:
            self.store.transition(job['payment_id'], 'creating', 'registered',
                                  receipt_uuid=uuid, last_error=None)

    def _reconcile(self, job):
        try:
            uuid = self.mynalog.find_income(self._receipt_name(job), job['amount'],
                                            parse_time(job['paid_at']))
        except (TemporaryFailure, PermanentFailure) as error:
            self.store.transition(job['payment_id'], 'unknown', 'unknown', last_error=str(error))
            return
        if uuid:
            self.store.transition(job['payment_id'], 'unknown', 'registered',
                                  receipt_uuid=uuid, last_error=None)

    def _email(self, job):
        if not self.settings.email_enabled:
            return
        current = job['state']
        if current == 'registered' and not self.store.transition(
                job['payment_id'], 'registered', 'email_pending'):
            return
        url = 'https://lknpd.nalog.ru/api/v1/receipt/{}/{}/print'.format(
            self.settings.mynalog_inn, job['receipt_uuid'])
        try:
            self.mailer.send(job['customer_email'], url)
        except Exception as error:
            self.store.transition(job['payment_id'], 'email_pending', 'email_pending',
                                  last_error='Receipt email failed: {}'.format(type(error).__name__))
            logger.warning('Receipt email failed for payment %s: %s', job['payment_id'], type(error).__name__)
        else:
            # The address is needed for retry only. Remove it after delivery.
            self.store.transition(job['payment_id'], 'email_pending', 'emailed',
                                  customer_email=None, last_error=None)

    def _send_problem_alerts(self):
        recipient = getattr(self.settings, 'admin_email', '')
        if not recipient:
            return
        for job in self.store.jobs('unknown', 'manual_review', 'email_pending'):
            if job['state'] == 'email_pending' and not job.get('last_error'):
                continue
            if job.get('alert_sent_at'):
                continue
            subject = 'Проверка чека YogaDailyBot'
            body = ('Платёж {} требует ручной проверки.\n'
                    'Состояние: {}\nОшибка: {}\n').format(
                        job['payment_id'], job['state'], job.get('last_error') or 'не указана')
            try:
                self.mailer.send_alert(recipient, subject, body)
            except Exception as error:
                logger.warning('Admin alert failed for payment %s: %s',
                               job['payment_id'], type(error).__name__)
            else:
                self.store.mark_alert_sent(job['payment_id'])

    def run_forever(self):
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception('Receipt synchronization cycle failed')
            time.sleep(self.settings.poll_seconds)
