"""Read-only preview and explicitly invoked activation helpers."""

from datetime import datetime

from .rules import launch_offer, registration_cutoff


def preview(cursor, launch_at: datetime):
    cursor.execute("SELECT COUNT(*) FROM users WHERE created_at < %s",
                   (registration_cutoff(launch_at),))
    count = cursor.fetchone()[0]
    return count, launch_offer(launch_at)
