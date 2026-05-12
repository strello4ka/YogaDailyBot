"""Обработчики кнопки «Мой прогресс» и сброса прогресса."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from data.db import (
    get_completed_count,
    get_total_practices,
    get_similar_result_percent,
    reset_user_progress,
)


def _progress_text(user_id: int) -> str:
    """Формирует текст прогресса «N из M»."""
    n = get_completed_count(user_id)
    m = get_total_practices(user_id)

    if m == 0:
        return "Ты еще не выполнил ни одной практики, все самое прекрасное впереди✨"
    return f"Выполнено практик: *{n} из {m}*"


def _similar_result_line(user_id: int) -> str:
    """Текст про долю пользователей с таким же результатом."""
    if get_completed_count(user_id) == 0:
        return ""
    m = get_total_practices(user_id)
    if m < 3:
        return "\n\\*уже считаю сколько пользователей с таким же результатом\\*"

    similar_percent = get_similar_result_percent(user_id, bucket_size=5, min_received=3)
    if similar_percent is None:
        return "\n\\*уже считаю сколько пользователей с таким же результатом\\*"

    if similar_percent < 1:
        return "\n*Менее 1%* пользователей YogaDailyBot имеют такой же результат..Ты неповторим!"

    return f"\nТакой же результат сейчас у *{round(similar_percent)}%* пользователей YogaDailyBot"


def _progress_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой «Сбросить прогресс»."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Сбросить прогресс", callback_data="progress_reset")]
    ])


def _confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения сброса."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Да, сбросить", callback_data="progress_reset_yes")],
        [InlineKeyboardButton("Нет", callback_data="progress_reset_no")]
    ])


async def handle_progress_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки «Мой прогресс»: показывает прогресс и кнопку сброса."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        return
    msg = update.effective_message
    if not msg:
        return
    text = _progress_text(user_id)
    text += _similar_result_line(user_id)
    reply_markup = None if get_completed_count(user_id) == 0 else _progress_keyboard()
    await msg.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_progress_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """По нажатию «Сбросить прогресс» — показать подтверждение."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.edit_message_text(
        "Точно хочешь сбросить? Практики будут приходить как раньше, просто цифры начнутся заново.",
        reply_markup=_confirm_keyboard()
    )


async def handle_progress_reset_yes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """По нажатию «Да, сбросить» — сброс прогресса и ответ."""
    query = update.callback_query
    if not query:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await query.answer("Ошибка.")
        return
    reset_user_progress(user_id)
    await query.answer()
    await query.edit_message_text("Готово, прогресс сброшен. Следующая практика придёт по расписанию как обычно. Новый старт - новый настрой!")


async def handle_progress_reset_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """По нажатию «Отмена» — убрать подтверждение."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.edit_message_text("Оки, оставляем как есть. Продолжай в том же духе!")
