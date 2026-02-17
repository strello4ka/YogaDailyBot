"""Обработчик кнопки «Выполнено» под сообщением с практикой."""

from telegram import Update
from telegram.ext import ContextTypes

from data.db import mark_practice_completed_today, get_completed_count, get_user_days


async def handle_practice_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия «Выполнено»: отмечает последнюю практику выполненной и показывает прогресс."""
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
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Так держать! Выполнено {n} из {m}",
        )
