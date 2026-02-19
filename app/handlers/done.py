"""Обработчик кнопки «✔️Я сделал!» под сообщением с практикой."""

from telegram import Update
from telegram.ext import ContextTypes

from data.db import mark_practice_completed_today, get_completed_count, get_user_days, get_user_rank


def _rank_line(user_id: int) -> str:
    """Строка «Твое место среди всех пользователей: X из Y» или пусто."""
    rank, total = get_user_rank(user_id)
    if rank is not None and total is not None:
        return f"\nТвое место в YogaDailyBot: *{rank} из {total}*"
    return ""


async def handle_practice_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия «✔️Я сделал!»: отмечает последнюю практику выполненной и показывает прогресс."""
    query = update.callback_query
    if not query:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await query.answer("Ошибка: пользователь не определён.")
        return

    ok = mark_practice_completed_today(user_id)
    await query.answer()  # убираем «часики» на кнопке, без всплывающего текста
    if ok:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        n = get_completed_count(user_id)
        m = get_user_days(user_id)
        rank_line = _rank_line(user_id)
        text = f"Ты супер🧡\n\nВыполнено практик: *{n} из {m}* {rank_line}"
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode='Markdown',
        )
