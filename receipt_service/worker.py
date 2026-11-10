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
        discovery_error = None
        try:
            discovered = self._discover_payments(now)
        except Exception as error:
            # Collection and delivery are independent. Existing receipts must
            # keep progressing even while YooKassa is unavailable. Report the
            # failed collection after draining the durable queue, not as success.
            discovery_error = error
            discovered = 0

        for job in self.store.jobs('unknown'):
            self._reconcile(job)
        for job in self.store.jobs('ready'):
            self._register(job)
        for job in self.store.jobs('registered', 'email_pending'):
            self._email(job)
        self._send_problem_alerts()
        counts = self.store.counts()
        logger.info('Receipt cycle complete: discovered=%s states=%s', discovered, counts)
        if discovery_error is not None:
            raise discovery_error
        return {'discovered': discovered, 'states': counts}

    def _discover_payments(self, now):
        checkpoint = self.store.get_value('yookassa_checkpoint')
        saved_floor = self.store.get_value('yookassa_sync_from')
        floor = parse_time(saved_floor) if saved_floor else self.settings.sync_from
        if saved_floor is None:
            # Keep the initial cutoff stable across restarts. For an existing
            # installation, preserve its checkpoint even after a long outage.
            if checkpoint:
                floor = min(floor, parse_time(checkpoint) - timedelta(minutes=10))
            self.store.set_value('yookassa_sync_from', floor.isoformat())
        # Re-read a small overlap; payment_id uniqueness makes this safe.
        # A saved checkpoint also survives outages longer than the default
        # rolling sync_from (24 hours at process startup).
        start = (max(floor, parse_time(checkpoint) - timedelta(minutes=10))
                 if checkpoint else floor)
        discovered = 0
        for payment in self.yookassa.successful_payments(start, now):
            self.store.add_payment(payment)
            discovered += 1
        self.store.set_value('yookassa_checkpoint', now.isoformat())
        return discovered

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
        except Exception as error:
            # Once a write was attempted, an unexpected adapter failure is
            # ambiguous too. Reconcile instead of leaving a stranded job or
            # risking another POST. Do not persist arbitrary response bodies.
            self.store.transition(job['payment_id'], 'creating', 'unknown',
                                  last_error='Unexpected write failure: ' + type(error).__name__)
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
        except Exception as error:
            self.store.transition(job['payment_id'], 'unknown', 'unknown',
                                  last_error='Receipt lookup failed: ' + type(error).__name__)
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
