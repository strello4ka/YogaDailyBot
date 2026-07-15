"""Кнопка «strello4ka»: практики только с канала владельца бота."""

from telegram import Update
from telegram.ext import ContextTypes

from data.db import pick_random_combined_mood_pool

from .send_utils import deliver_by_mood_practice

FILTER_KEY = "strello4ka"
WHERE = " AND LOWER(TRIM(COALESCE(yp.channel_name, ''))) LIKE %s "
PARAMS = ("%strello4ka%",)


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    row = pick_random_combined_mood_pool(user.id, FILTER_KEY, WHERE, PARAMS)
    if not row:
        await update.message.reply_text(
            "Не нашлось практик от strello4ka. Попробуй другой фильтр."
        )
        return
    ok = await deliver_by_mood_practice(context, chat.id, user.id, FILTER_KEY, row)
    if not ok:
        await update.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")
