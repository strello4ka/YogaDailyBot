"""Админ-команда превью воскресного расписания."""

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.secret import ADMIN_USER_ID
from app.challenge.week_schedule.job import send_challenge_weekly_schedule


async def challenge_schedule_preview_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет расписание на неделю сразу (без ожидания вс 20:00), не меняя флаги."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    ok = await send_challenge_weekly_schedule(context, force=True)
    if ok:
        await update.message.reply_text("✅ Превью расписания отправлено в групповой чат.")
    else:
        await update.message.reply_text(
            "❌ Не удалось отправить расписание. Проверь CHALLENGE_GROUP_CHAT_ID, участников и challenge_start_id."
        )
