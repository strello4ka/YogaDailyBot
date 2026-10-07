"""Persist onboarding state in the existing system_state table."""

import json
from data.postgres_db import get_connection, _tomorrow_date_moscow

PREFIX = "onboarding_v3:"


def load_state(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM system_state WHERE key=%s", (f"{PREFIX}{user_id}",))
            row = cur.fetchone()
            return json.loads(row[0]) if row else None
    finally:
        conn.close()


def save_state(state, *, schedule_time=None, complete=False):
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                if schedule_time is not None:
                    cur.execute(
                        """UPDATE users SET notify_time=%s, bot_mode='daily', daily_schedule_enabled=TRUE,
                        first_daily_send_date=%s, updated_at=CURRENT_TIMESTAMP WHERE user_id=%s""",
                        (schedule_time, _tomorrow_date_moscow(), state["user_id"]),
                    )
                if complete:
                    cur.execute(
                        """UPDATE users SET onboarding_required=FALSE,
                        notify_time=CASE WHEN bot_mode='pending' THEN '00:00' ELSE notify_time END,
                        daily_schedule_enabled=CASE WHEN bot_mode='pending' THEN FALSE ELSE daily_schedule_enabled END,
                        bot_mode=CASE WHEN bot_mode='pending' THEN 'by_mood' ELSE bot_mode END,
                        updated_at=CURRENT_TIMESTAMP WHERE user_id=%s""",
                        (state["user_id"],),
                    )
                cur.execute(
                    """INSERT INTO system_state(key,value) VALUES(%s,%s)
                    ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value""",
                    (f"{PREFIX}{state['user_id']}", json.dumps(state, ensure_ascii=False)),
                )
    finally:
        conn.close()


def pending_states():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT s.value FROM system_state s
                JOIN users u ON s.key = %s || u.user_id::text
                WHERE COALESCE(u.is_blocked, FALSE) = FALSE""",
                (PREFIX,),
            )
            return [json.loads(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()
