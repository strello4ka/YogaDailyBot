"""Callbacks and free-form feedback used by the one-off old-user launch."""

import asyncio
import json
import time

from app.handlers.help import FREE_MODE_FAQ_TEXT, SUBSCRIPTION_FAQ_TEXT

from .messages import (FEEDBACK_CALLBACK, FREE_DETAILS_CALLBACK,
                       SUBSCRIPTION_DETAILS_CALLBACK)

WAITING_FOR_FEEDBACK = "waiting_for_old_user_feedback"
FEEDBACK_STATE_PREFIX = "old_user_feedback_wait:"
FEEDBACK_WAIT_SECONDS = 24 * 60 * 60


def _feedback_state_key(user_id):
    return f"{FEEDBACK_STATE_PREFIX}{user_id}"


def _begin_feedback_wait(user_id):
    from data.postgres_db import _set_system_state
    _set_system_state(
        _feedback_state_key(user_id),
        json.dumps({"entered_at": time.time()}),
    )


def _load_feedback_wait(user_id):
    from data.postgres_db import _get_system_state
    raw = _get_system_state(_feedback_state_key(user_id))
    return json.loads(raw) if raw else None


def _clear_feedback_wait(user_id):
    from data.postgres_db import _delete_system_state
    return _delete_system_state(_feedback_state_key(user_id))


async def access_details_callback(update, context):
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()
    text = {
        SUBSCRIPTION_DETAILS_CALLBACK: SUBSCRIPTION_FAQ_TEXT,
        FREE_DETAILS_CALLBACK: FREE_MODE_FAQ_TEXT,
    }.get(query.data)
    if text:
        await query.message.reply_text(text)


async def feedback_callback(update, context):
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()
    for key in ("waiting_for_practice_suggestion", "waiting_for_time",
                "waiting_for_schedule_menu_time", "is_time_change"):
        context.user_data.pop(key, None)
    await asyncio.to_thread(_begin_feedback_wait, update.effective_user.id)
    context.user_data[WAITING_FOR_FEEDBACK] = True
    await query.message.reply_text("Напиши мне любой текст.")


async def cancel_feedback_wait(update, context):
    """Cancel feedback input after an explicit command, button or callback."""
    user = update.effective_user
    if not user:
        return
    callback = getattr(update, "callback_query", None)
    if callback and (callback.data or "") == FEEDBACK_CALLBACK:
        return
    await asyncio.to_thread(_clear_feedback_wait, user.id)
    context.user_data.pop(WAITING_FOR_FEEDBACK, None)


def _save_feedback(user_id, username, text):
    from data.postgres_db import get_connection
    from .repository import save_feedback

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            save_feedback(cursor, user_id, username, text)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


async def handle_feedback_input(update, context):
    """Consume one text message after the feedback button was pressed."""
    if not update.effective_chat or update.effective_chat.type != "private":
        return False
    state = await asyncio.to_thread(_load_feedback_wait, update.effective_user.id)
    if not state:
        context.user_data.pop(WAITING_FOR_FEEDBACK, None)
        return False
    if time.time() >= state.get("entered_at", 0) + FEEDBACK_WAIT_SECONDS:
        await asyncio.to_thread(_clear_feedback_wait, update.effective_user.id)
        context.user_data.pop(WAITING_FOR_FEEDBACK, None)
        return False
    context.user_data[WAITING_FOR_FEEDBACK] = True
    text = (update.effective_message.text or "").strip()
    if not text:
        await update.effective_message.reply_text("Напиши мне любой текст.")
        return True
    try:
        await asyncio.to_thread(
            _save_feedback,
            update.effective_user.id,
            update.effective_user.username,
            text,
        )
    except Exception:
        await update.effective_message.reply_text(
            "Не получилось сохранить сообщение. Попробуй ещё раз."
        )
        return True
    context.user_data.pop(WAITING_FOR_FEEDBACK, None)
    await asyncio.to_thread(_clear_feedback_wait, update.effective_user.id)
    await update.effective_message.reply_text(
        "Спасибо за твою обратную связь 🧡\n"
        "Я обязательно всё прочитаю и учту."
    )
    return True
