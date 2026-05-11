"""Модуль челленджа: команды /challenge и /challenge_off, выбор практики для ежедневной рассылки.

Функции БД (get_user_challenge_start_id, set_user_challenge, clear_user_challenge,
get_yoga_practice_by_id, get_yoga_practice_by_challenge_order и т.д.) остаются в data.postgres_db.
"""

import logging
import re
from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from app.keyboards import MODE_CHOICE_INTRO_MARKDOWN, get_mode_choice_keyboard, get_welcome_keyboard

from data.db import (
    get_yoga_practice_by_id,
    clear_user_challenge,
    get_user_challenge_start_id,
    get_yoga_practice_by_challenge_order,
)

logger = logging.getLogger(__name__)

PENDING_CHALLENGE_PRACTICE_KEY = "pending_challenge_practice_id"


async def begin_challenge_time_selection_flow(
    update: Update, context: ContextTypes.DEFAULT_TYPE, practice_id: int
) -> None:
    """Единый вход в челлендж: приветствие + inline «Выбрать время»; id практики храним до ввода времени."""
    chat_id = update.effective_chat.id
    context.user_data[PENDING_CHALLENGE_PRACTICE_KEY] = practice_id
    welcome_text = (
        "Приветствую в *челлендже* 🧡\n\n"
        "Каждый день в выбранное время ты будешь получать следующую практику по цепочке "
        "от той, с которой начинаешь.\n\n"
        "*Выбери время для челленджа:* нажми кнопку ниже и введи время в формате *ЧЧ.ММ* (по МСК)."
    )
    time_choice_message = await update.message.reply_text(
        welcome_text,
        reply_markup=get_welcome_keyboard(),
        parse_mode="Markdown",
    )
    context.user_data["daily_time_choice_chat_id"] = chat_id
    context.user_data["daily_time_choice_message_id"] = time_choice_message.message_id


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
    await _start_challenge(update, context, user_id, practice_id)


async def challenge_compact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда челленджа в формате /challenge<id>, например /challenge61."""
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    match = re.match(r"^/challenge(?:@[\w_]+)?(\d+)$", text)
    if not match:
        return
    practice_id = int(match.group(1))
    await _start_challenge(update, context, user_id, practice_id)


async def _start_challenge(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, practice_id: int
):
    """Запуск челленджа: для всех режимов один сценарий — приветствие и выбор времени, затем включение в БД после ввода времени."""
    if practice_id < 1:
        await update.message.reply_text("Id практики должен быть положительным числом.")
        return
    practice = get_yoga_practice_by_id(practice_id)
    if not practice:
        await update.message.reply_text(f"Упс, что-то не то. Попробуй другую команду")
        return
    await begin_challenge_time_selection_flow(update, context, practice_id)
    logger.info(
        "Пользователь %s открыл экран выбора времени для челленджа (practice_id=%s)",
        user_id,
        practice_id,
    )


async def challenge_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из режима челленджа: рассылка снова по дням недели и выбор режима Daily / By mood."""
    user_id = update.effective_user.id
    clear_user_challenge(user_id)
    await update.message.reply_text(
        "Режим челленджа завершен ✔️\n"
        "Какой бы ни был твой результат, ты мега крут!\n"
        "Практики в Daily снова будут приходить в обычном порядке по дням недели.\n\n"
        "Выбери, как дальше работать с ботом:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        MODE_CHOICE_INTRO_MARKDOWN,
        reply_markup=get_mode_choice_keyboard(),
        parse_mode="Markdown",
    )
    logger.info(f"Пользователь {user_id} выключил челлендж")
