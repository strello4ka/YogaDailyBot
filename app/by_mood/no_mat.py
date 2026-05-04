"""Кнопка «без коврика»: практики с признаком without_mat в БД."""

from telegram import Update
from telegram.ext import ContextTypes

from data.db import pick_random_by_mood_practice

from .send_utils import deliver_by_mood_practice

FILTER_KEY = "no_mat"
WHERE = " AND yp.without_mat = TRUE "


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    row = pick_random_by_mood_practice(user.id, FILTER_KEY, WHERE, ())
    if not row:
        await update.message.reply_text(
            "Пока нет практик с отметкой «без коврика» в базе. Как только добавим — фильтр заработает."
        )
        return
    ok = await deliver_by_mood_practice(context, chat.id, user.id, FILTER_KEY, row)
    if not ok:
        await update.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")
