"""Общее завершение челленджа и предложение обычного расписания."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Optional

from telegram.ext import ContextTypes

from app.challenge.cohort import CHALLENGE_DURATION
from data.db import clear_user_challenge, get_connection

logger = logging.getLogger(__name__)


def build_challenge_finished_text(completed: Optional[int] = None) -> str:
    """Текст завершения челленджа; completed — личный N из 28 (опционально)."""
    result_line = ""
    if completed is not None:
        result_line = f"Твой результат: *{completed}/{CHALLENGE_DURATION}* дней\n"
    return (
        "*Челлендж завершен* ✅\n\n"
        f"{result_line}"
        "Какими бы ни были цифры, мы классно провели время 🧡\n\n"
        "Продолжай пользоваться со мной, чтобы сохранить привычку."
    )


async def finish_challenge_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    chat_id: int,
    completed: Optional[int] = None,
) -> bool:
    """Выход: результат, затем отложенное предложение обычного расписания."""
    from app.daily.extra_practices import strip_extra_practices_inline_keyboards
    from app.handlers.done import cancel_done_reminders, dismiss_done_reminders

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT notify_time FROM users WHERE user_id=%s", (user_id,))
            row = cursor.fetchone()
            raw_time = row[0] if row and row[0] else "09:00"
            previous_time = raw_time.strftime("%H:%M") if hasattr(raw_time, "strftime") else str(raw_time)[:5]
    finally:
        conn.close()

    if not clear_user_challenge(user_id):
        logger.error(
            "Не удалось сохранить завершение челленджа user=%s; финальное сообщение не отправлено",
            user_id,
        )
        return False
    await cancel_done_reminders(context, user_id)
    dismiss_done_reminders(user_id)
    await strip_extra_practices_inline_keyboards(context.bot, user_id)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_challenge_finished_text(completed),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Не удалось отправить завершение челленджа user=%s: %s", user_id, e)
        return False

    from app.challenge.flow.post_challenge import delayed_offer_job, save
    if not save({"user_id": user_id, "chat_id": chat_id, "time": previous_time, "stage": "waiting", "entered_at": time.time(), "reminded": []}):
        logger.error("Не удалось сохранить post-challenge offer user=%s", user_id)
        return False
    if context.job_queue is not None:
        context.job_queue.run_once(delayed_offer_job, timedelta(seconds=10), data={"user_id": user_id})
    return True
