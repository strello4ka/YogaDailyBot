"""Обработчики кнопки «Мой прогресс» и сброса прогресса."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from data.db import get_completed_count, get_user_days, get_user_rank, reset_user_progress


def _rank_line(user_id: int) -> str:
    """Строка «Твое место среди всех пользователей: X из Y» или пусто, если ранг ещё не посчитан."""
    rank, total = get_user_rank(user_id)
    if rank is not None and total is not None:
        return f"\nТвое место среди всех пользователей: *{rank} из {total}*"
    return ""


def _progress_text(user_id: int) -> str:
    """Формирует текст прогресса «N из M» (без фразы про гордость — она добавляется в обработчике при необходимости)."""
    n = get_completed_count(user_id)
    m = get_user_days(user_id)
    if m == 0:
        return "Ты еще не выполнил ни одной практики, все самое прекрасное впереди✨"
    return f"Твой прогресс: *{n} из {m}* практик✨"


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


def _progress_proud_suffix(user_id: int) -> str:
    """Добавляет «Невероятно! Я горжусь тобой.» в конце сообщения «Мой прогресс», если n=m или место 1–5."""
    n = get_completed_count(user_id)
    m = get_user_days(user_id)
    rank, _ = get_user_rank(user_id)
    if (m > 0 and n == m) or (rank is not None and 1 <= rank <= 5):
        return "\n\nНевероятно! Я горжусь тобой."
    return ""


async def handle_progress_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки «Мой прогресс»: показывает прогресс и кнопку сброса."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        return
    text = _progress_text(user_id) + _rank_line(user_id) + _progress_proud_suffix(user_id)
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
