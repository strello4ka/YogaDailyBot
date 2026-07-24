"""Запасные ручные команды: /challenge и /challenge_off."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.challenge.cohort import (
    CHALLENGE_DURATION,
    enrollment_closed_message,
    get_challenge_start_practice_id,
    is_challenge_enrollment_open,
    is_cohort_configured,
)
from app.challenge.flow.exit_flow import finish_challenge_for_user
from app.challenge.flow.start_flow import (
    CHALLENGE_TIME_FLOW_KEY,
    PENDING_CHALLENGE_PRACTICE_KEY,
    begin_challenge_time_selection_flow,
)
from data.db import get_challenge_completed_in_last_n_days, get_yoga_practice_by_id

logger = logging.getLogger(__name__)


async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запасной ручной запуск челленджа для одного пользователя (/challenge).

    Основной способ записи — `/flow_add`. Id практики только из env.
    """
    user_id = update.effective_user.id
    if not is_cohort_configured() or not is_challenge_enrollment_open():
        await update.message.reply_text(enrollment_closed_message())
        return

    practice_id = get_challenge_start_practice_id()
    practice = get_yoga_practice_by_id(practice_id)
    if not practice:
        await update.message.reply_text("Упс, что-то не то. Попробуй другую команду")
        return
    await begin_challenge_time_selection_flow(update, context, practice_id)
    logger.info(
        "Пользователь %s открыл экран выбора времени для челленджа (practice_id=%s)",
        user_id,
        practice_id,
    )


async def challenge_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запасной досрочный выход из челленджа (/challenge_off).

    Основное завершение потока — автозавершение на день 29.
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    context.user_data.pop(PENDING_CHALLENGE_PRACTICE_KEY, None)
    context.user_data.pop(CHALLENGE_TIME_FLOW_KEY, None)
    context.user_data.pop("waiting_for_time", None)

    completed = get_challenge_completed_in_last_n_days(user_id, CHALLENGE_DURATION)
    await finish_challenge_for_user(
        context, user_id=user_id, chat_id=chat_id, completed=completed
    )
    logger.info(
        "Пользователь %s выключил челлендж (результат %s/%s)",
        user_id,
        completed,
        CHALLENGE_DURATION,
    )
