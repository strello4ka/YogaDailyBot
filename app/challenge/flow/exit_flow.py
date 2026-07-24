"""Общее завершение челленджа: текст, pending, выбор режима, напоминания."""

from __future__ import annotations

import logging
from typing import Optional

from telegram import ReplyKeyboardRemove
from telegram.ext import ContextTypes

from app.challenge.cohort import CHALLENGE_DURATION
from app.keyboards import get_mode_choice_keyboard
from data.db import clear_user_challenge

logger = logging.getLogger(__name__)


def build_challenge_finished_text(completed: Optional[int] = None) -> str:
    """Текст завершения челленджа; completed — личный N из 28 (опционально)."""
    result_line = ""
    if completed is not None:
        result_line = f"Твой результат: *{completed}/{CHALLENGE_DURATION}* дней\n"
    return (
        "Челлендж завершен ✔️\n"
        f"{result_line}"
        "Какими бы ни были цифры, я так рад, что ты участвовал!\n"
        "Продолжай пользоваться мной, чтобы сохранить привычку. \n"
        "Твой прогресс челленджа будет сохранен.\n\n"
        "Выбери, как дальше работать с ботом 👇"
    )


async def finish_challenge_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    chat_id: int,
    completed: Optional[int] = None,
) -> bool:
    """Выход из челленджа: clear + сообщение + выбор режима + напоминания."""
    from app.onboarding import MODE_CHOICE_INTRO_MARKDOWN, schedule_mode_pick_reminders
    from app.daily.extra_practices import strip_extra_practices_inline_keyboards

    clear_user_challenge(user_id)
    await strip_extra_practices_inline_keyboards(context.bot, user_id)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_challenge_finished_text(completed),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown",
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=MODE_CHOICE_INTRO_MARKDOWN,
            reply_markup=get_mode_choice_keyboard(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Не удалось отправить завершение челленджа user=%s: %s", user_id, e)
        return False

    if hasattr(context, "job_queue") and context.job_queue is not None:
        await schedule_mode_pick_reminders(context, chat_id, user_id)
    return True
