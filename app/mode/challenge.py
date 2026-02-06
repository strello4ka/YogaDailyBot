"""Модуль челленджа: команды /challenge и /challenge_off, выбор практики для ежедневной рассылки.

Функции БД (get_user_challenge_start_id, set_user_challenge, clear_user_challenge,
get_yoga_practice_by_id, get_yoga_practice_by_challenge_order и т.д.) остаются в data.postgres_db.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from data.db import (
    get_yoga_practice_by_id,
    set_user_challenge,
    clear_user_challenge,
    get_user_notify_time,
    get_user_challenge_start_id,
    get_yoga_practice_by_challenge_order,
)

logger = logging.getLogger(__name__)


def get_practice_for_daily_send(user_id: int, weekday: int, day_number: int):
    """Возвращает практику для рассылки, если пользователь в режиме челленджа; иначе None.

    Используется планировщиком: если вернул (practice, True), отправлять эту практику;
    если (None, False) — планировщик берёт практику по дню недели.

    Returns:
        tuple: (practice или None, is_challenge: bool)
    """
    start_id = get_user_challenge_start_id(user_id)
    if start_id is None:
        return (None, False)
    practice = get_yoga_practice_by_challenge_order(start_id, day_number)
    return (practice, True)


async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда челленджа: /challenge <id>. Без id — никакого ответа."""
    user_id = update.effective_user.id
    if not context.args or len(context.args) != 1:
        return
    try:
        practice_id = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("Нужно указать число — id практики. Пример: /challenge 54")
        return
    if practice_id < 1:
        await update.message.reply_text("Id практики должен быть положительным числом.")
        return
    practice = get_yoga_practice_by_id(practice_id)
    if not practice:
        await update.message.reply_text(f"Практики с id {practice_id} нет в базе. Укажи существующий id.")
        return
    notify_time = get_user_notify_time(user_id)
    if notify_time is None:
        await update.message.reply_text(
            "Сначала пройди онбординг: нажми /start и укажи время, в которое хочешь получать практики. "
            "После этого можно будет включить челлендж."
        )
        return
    if not set_user_challenge(user_id, practice_id):
        await update.message.reply_text("Не удалось включить режим челленджа. Попробуй позже.")
        return
    time_text = f"завтра в {notify_time}"
    await update.message.reply_text(
        f"Челлендж включён с практики id {practice_id}.\n\n"
        f"{time_text} придёт практика челленджа (день 1). Дальше каждый день — следующая по порядку id; когда список закончится — снова с id 1.\n\n"
        "Чтобы вернуться к обычной рассылке по дням недели, напиши /challenge_off"
    )
    logger.info(f"Пользователь {user_id} включил челлендж с id={practice_id}")


async def challenge_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из режима челленджа: рассылка снова по дням недели."""
    user_id = update.effective_user.id
    clear_user_challenge(user_id)
    await update.message.reply_text(
        "Режим челленджа выключен. Практики снова будут приходить по дням недели в обычном порядке.\n"
        "Чтобы снова включить челлендж с любого id — напиши /challenge <id>"
    )
    logger.info(f"Пользователь {user_id} выключил челлендж")
