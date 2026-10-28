#!/usr/bin/env python3
"""Preview or explicitly activate the one-off old-users cohort."""

import argparse
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.subscription.old_users.activation import preview
from app.subscription.old_users.repository import enroll
from app.subscription.tariff import MOSCOW
from data.postgres_db import get_connection

CONFIRMATION = "ACTIVATE_OLD_USERS"


def parse_launch_date(value):
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=MOSCOW)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-date", required=True, type=parse_launch_date)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if args.apply and args.confirm != CONFIRMATION:
        parser.error("--apply requires --confirm {}".format(CONFIRMATION))

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            count, offer = preview(cursor, args.launch_date)
            print("Users: {}".format(count))
            print("Gift: {} — {}".format(offer.gift.starts_at, offer.gift.ends_at))
            print("Special prices until: {}".format(offer.offer_ends))
            if args.apply:
                changed = enroll(cursor, args.launch_date)
                connection.commit()
                print("Activated: {}".format(changed))
            else:
                connection.rollback()
                print("Preview only; no data changed")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
