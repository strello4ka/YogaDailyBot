import argparse
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
    if args.once:
        print(json.dumps(worker.run_once(), ensure_ascii=False, sort_keys=True))
    else:
        worker.run_forever()


if __name__ == '__main__':
    main()
