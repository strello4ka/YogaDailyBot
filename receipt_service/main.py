import argparse
from dataclasses import replace
import json
import logging
import os
from pathlib import Path

from receipt_service.config import Settings
from receipt_service.mailer import ReceiptMailer
from receipt_service.providers import MyNalogClient, YooKassaReader
from receipt_service.state import StateStore
from receipt_service.worker import ReceiptWorker


def build_worker(settings):
    Path(settings.state_path).parent.mkdir(parents=True, exist_ok=True)
    store = StateStore(settings.state_path)
    recovered = store.recover_interrupted_writes()
    if recovered:
        logging.warning('Moved %s interrupted My Nalog writes to reconciliation', recovered)
    saved_refresh = store.get_value('mynalog_refresh_token')
    mynalog = MyNalogClient(saved_refresh or settings.mynalog_refresh_token,
                            settings.mynalog_device_id,
                            on_refresh_token=lambda token: store.set_value('mynalog_refresh_token', token))
    mailer = ReceiptMailer(settings.smtp_host, settings.smtp_port, settings.smtp_user,
                           settings.smtp_password, settings.smtp_from)
    return ReceiptWorker(settings, store,
                         YooKassaReader(settings.yookassa_shop_id, settings.yookassa_secret_key),
                         mynalog, mailer)


def run_backfill(worker, settings):
    values = (settings.backfill_payment_id, settings.backfill_email,
              settings.backfill_service_name)
    if not any(values):
        return
    if not all(values):
        raise ValueError('All RECEIPT_BACKFILL_* variables are required')
    for name in ('mynalog_refresh_token', 'mynalog_device_id', 'mynalog_inn',
                 'smtp_host', 'smtp_user', 'smtp_password', 'smtp_from'):
        if not getattr(settings, name):
            raise ValueError(f'{name} is required for receipt backfill')

    payment = worker.yookassa.successful_payment(settings.backfill_payment_id)
    payment['metadata'] = {
        'order_id': (payment.get('metadata') or {}).get('order_id') or payment['id'],
        'customer_email': settings.backfill_email,
        'service_name': settings.backfill_service_name,
    }
    worker.store.add_payment(payment)

    one_shot = ReceiptWorker(replace(settings, mynalog_writes_enabled=True, email_enabled=True),
                             worker.store, worker.yookassa, worker.mynalog, worker.mailer)
    job = worker.store.job(settings.backfill_payment_id)
    if job['state'] == 'unknown':
        one_shot._reconcile(job)
        job = worker.store.job(settings.backfill_payment_id)
    if job['state'] == 'ready':
        one_shot._register(job)
        job = worker.store.job(settings.backfill_payment_id)
    if job['state'] in {'registered', 'email_pending'}:
        one_shot._email(job)
        job = worker.store.job(settings.backfill_payment_id)
    logging.info('Backfill payment %s finished in state=%s', payment['id'], job['state'])


def main():
    parser = argparse.ArgumentParser(description='YooKassa to My Nalog receipt service')
    parser.add_argument('--once', action='store_true', help='run one synchronization cycle and exit')
    parser.add_argument('--status', action='store_true', help='show local queue status without network calls')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if args.status:
        store = StateStore(os.getenv('RECEIPT_STATE_PATH', '/data/receipts.sqlite3'))
        print(json.dumps(store.counts(), ensure_ascii=False, sort_keys=True))
        return
    settings = Settings.from_env()
    if not settings.mynalog_writes_enabled:
        logging.warning('MYNALOG_WRITES_ENABLED=false: payments are collected, receipts are not created')
    worker = build_worker(settings)
    if settings.mynalog_auth_check_on_start:
        worker.mynalog.authenticate()
        logging.info('My Nalog authentication check succeeded')
    run_backfill(worker, settings)
    if args.once:
        print(json.dumps(worker.run_once(), ensure_ascii=False, sort_keys=True))
    else:
        worker.run_forever()


if __name__ == '__main__':
    main()
