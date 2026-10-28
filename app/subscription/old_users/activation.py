"""Read-only preview and explicitly invoked activation helpers."""

from datetime import datetime

from ..tariff import local_time
from .rules import launch_offer


def preview(cursor, launch_at: datetime):
    launch_day = local_time(launch_at).date()
    cursor.execute("SELECT COUNT(*) FROM users WHERE created_at::date < %s", (launch_day,))
    count = cursor.fetchone()[0]
    return count, launch_offer(launch_at)
