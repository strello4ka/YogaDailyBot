"""Helpers for writing to the append-only product analytics journal."""

import json
import re

from data.postgres_db import get_connection


_EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def record_product_event(cursor, user_id, event_name, dedupe_key, *, occurred_at=None,
                         metadata=None):
    """Insert one logical event; retries with the same key are harmless."""
    if not _EVENT_NAME_RE.fullmatch(event_name):
        raise ValueError("Invalid product event name")
    cursor.execute(
        "INSERT INTO product_events(user_id,event_name,dedupe_key,occurred_at,metadata) "
        "VALUES(%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP),%s::jsonb) "
        "ON CONFLICT(user_id,event_name,dedupe_key) DO NOTHING",
        (user_id, event_name, str(dedupe_key), occurred_at,
         json.dumps(metadata or {}, ensure_ascii=False)),
    )


def record_product_event_for_user(user_id, event_name, dedupe_key, *, occurred_at=None,
                                  metadata=None):
    """Write one event in its own short transaction."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                record_product_event(
                    cursor,
                    user_id,
                    event_name,
                    dedupe_key,
                    occurred_at=occurred_at,
                    metadata=metadata,
                )
    finally:
        conn.close()
