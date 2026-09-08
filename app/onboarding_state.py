"""Сохраняемый этап онбординга в существующем system_state, без сброса данных."""

import json

from data.postgres_db import get_connection, _tomorrow_date_moscow

PREFIX = "onboarding_v2:"


def load_state(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT value FROM system_state WHERE key = %s", (f"{PREFIX}{user_id}",))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None
    finally:
        conn.close()


def save_state(state, *, create_user=False, schedule_time=None, complete=False):
    """Изменение состояния и пользователя в одной транзакции; ошибка не маскируется."""
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cursor:
                if create_user:
                    cursor.execute("""
                        INSERT INTO users (user_id, chat_id, notify_time, user_name, user_nickname,
                            onboarding_required, bot_mode, daily_schedule_enabled, traffic_source)
                        VALUES (%s, %s, '00:00', %s, %s, TRUE, 'pending', FALSE, %s)
                        ON CONFLICT (user_id) DO NOTHING
                    """, (state["user_id"], state["chat_id"], state.get("name"),
                          state.get("nickname"), state.get("traffic_source")))
                if schedule_time is not None:
                    cursor.execute("""
                        UPDATE users SET notify_time = %s, bot_mode = 'daily',
                            daily_schedule_enabled = TRUE, onboarding_required = FALSE,
                            first_daily_send_date = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = %s AND bot_mode != 'challenge'
                    """, (schedule_time, _tomorrow_date_moscow(), state["user_id"]))
                    if cursor.rowcount != 1:
                        raise ValueError("Пользователь отсутствует или уже вступил в челлендж")
                if complete:
                    cursor.execute("""
                        UPDATE users SET onboarding_required = FALSE,
                            bot_mode = CASE WHEN bot_mode = 'pending' THEN 'by_mood' ELSE bot_mode END
                        WHERE user_id = %s
                    """, (state["user_id"],))
                cursor.execute("""
                    INSERT INTO system_state (key, value) VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """, (f"{PREFIX}{state['user_id']}", json.dumps(state, ensure_ascii=False)))
    finally:
        conn.close()


def pending_states():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.value FROM system_state s
                JOIN users u ON s.key = %s || u.user_id::text
                WHERE COALESCE(u.is_blocked, FALSE) = FALSE
            """, (PREFIX,))
            states = [json.loads(row[0]) for row in cursor.fetchall()]
            return [s for s in states if s["step"] not in ("complete", "declined", "challenge")]
    finally:
        conn.close()
