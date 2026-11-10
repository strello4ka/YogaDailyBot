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
from app.subscription.tariff import MOSCOW, local_time
from data.postgres_db import get_connection

CONFIRMATION = "ACTIVATE_OLD_USERS"


def parse_launch_date(value):
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=MOSCOW)


def parse_launch_at(value):
    """Require an explicit timezone so activation cannot depend on host timezone."""
    return local_time(datetime.fromisoformat(value.replace('Z', '+00:00')))


def main():
    parser = argparse.ArgumentParser()
    launch = parser.add_mutually_exclusive_group(required=True)
    launch.add_argument("--launch-at", type=parse_launch_at,
                        help="Exact launch instant, e.g. 2026-11-10T15:00:00+03:00")
    launch.add_argument("--launch-date", type=parse_launch_date,
                        help="Compatibility mode: launch at 00:00 Moscow on this date")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    launch_at = args.launch_at if args.launch_at is not None else args.launch_date
    if args.apply and args.confirm != CONFIRMATION:
        parser.error("--apply requires --confirm {}".format(CONFIRMATION))

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            count, offer = preview(cursor, launch_at)
            print("Users: {}".format(count))
            print("Gift: {} — {}".format(offer.gift.starts_at, offer.gift.ends_at))
            print("Special prices until: {}".format(offer.offer_ends))
            if args.apply:
                changed = enroll(cursor, launch_at)
                connection.commit()
                print("Activated: {}".format(changed))
            else:
                connection.rollback()
                print("Preview only; no data changed")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
