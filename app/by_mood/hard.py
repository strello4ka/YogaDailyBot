"""Кнопка «хард»: высокая интенсивность."""

from telegram import Update
from telegram.ext import ContextTypes

from data.db import pick_random_by_mood_practice

from .send_utils import deliver_by_mood_practice

FILTER_KEY = "hard"
WHERE = " AND LOWER(TRIM(COALESCE(yp.intensity, ''))) IN ('высокая', 'высокий') "


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    row = pick_random_by_mood_practice(user.id, FILTER_KEY, WHERE, ())
    if not row:
        await update.message.reply_text(
            "Не нашлось практик с высокой интенсивностью. Попробуй другой фильтр."
        )
        return
    ok = await deliver_by_mood_practice(context, chat.id, user.id, FILTER_KEY, row)
    if not ok:
        await update.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")
