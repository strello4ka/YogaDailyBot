"""Модуль челленджа: команды /challenge и /challenge_off, выбор практики для ежедневной рассылки.

Функции БД (get_user_challenge_start_id, set_user_challenge, clear_user_challenge,
get_yoga_practice_by_id, get_yoga_practice_by_challenge_order и т.д.) остаются в data.postgres_db.
"""

import logging
import re
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
    """Команда челленджа: /challenge <id>."""
    user_id = update.effective_user.id
    if not context.args or len(context.args) != 1:
        return
    try:
        practice_id = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("Нужно указать число — id практики. Пример: /challenge 54")
        return
    await _start_challenge(update, user_id, practice_id)


async def challenge_compact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда челленджа в формате /challenge<id>, например /challenge61."""
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    match = re.match(r"^/challenge(?:@[\w_]+)?(\d+)$", text)
    if not match:
        return
    practice_id = int(match.group(1))
    await _start_challenge(update, user_id, practice_id)


async def _start_challenge(update: Update, user_id: int, practice_id: int):
    """Единая бизнес-логика запуска челленджа для разных форматов команды."""
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
            "Сначала пройди онбординг: нажми /start и выбери время, в которое хочешь получать практики. "
            "После этого можно будет запустить челлендж."
        )
        return
    if not set_user_challenge(user_id, practice_id):
        await update.message.reply_text("Не удалось включить режим челленджа. Попробуй позже.")
        return
    await update.message.reply_text(
        f"Челлендж запущен!\n"
        f"Завтра в {notify_time} придёт твоя практика.\n"
        "Удачи 🧡"
    )
    logger.info(f"Пользователь {user_id} включил челлендж с id={practice_id}")


async def challenge_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из режима челленджа: рассылка снова по дням недели."""
    user_id = update.effective_user.id
    clear_user_challenge(user_id)
    await update.message.reply_text(
        "Режим челленджа завершен ✔️\n"
        "Какой бы не был твой результат, ты супер!\n"
        "Практики снова будут приходить в обычном порядке. Изменить время всегда можно по кнопке в клавиатуре\n"
    )
    logger.info(f"Пользователь {user_id} выключил челлендж")
