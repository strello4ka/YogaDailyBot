"""Обработчики кнопки «Мой прогресс» и сброса прогресса."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from data.db import get_completed_count, get_user_days, get_user_rank, reset_user_progress


def _rank_line(user_id: int) -> str:
    """Строка «Твое место в YogaDailyBot: X из Y» или пусто, если ранг не посчитан или не выполнено ни одной практики."""
    if get_completed_count(user_id) == 0:
        return ""
    rank, total = get_user_rank(user_id)
    if rank is not None and total is not None:
        return f"\nТвое место в YogaDailyBot: *{rank} из {total}*"
    return ""


def _progress_text(user_id: int) -> str:
    """Формирует текст прогресса «N из M»."""
    n = get_completed_count(user_id)
    m = get_user_days(user_id)
    if m == 0:
        return "Ты еще не выполнил ни одной практики, все самое прекрасное впереди✨"
    return f"*Твой прогресс📈*\n\nВыполнено практик: *{n} из {m}*"


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
    text = _progress_text(user_id) + _rank_line(user_id)
    await update.message.reply_text(text, reply_markup=_progress_keyboard(), parse_mode='Markdown')


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
