"""Экран управления расписанием; внутренние режимы сохраняются."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from data.db import get_user_bot_mode, get_last_published_challenge_schedule


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_message:
        return
    rows = [
        [InlineKeyboardButton("Изменить время", callback_data="schedule_time")],
        [InlineKeyboardButton("Пауза", callback_data="schedule_pause")],
    ]
    if get_user_bot_mode(update.effective_user.id) == "challenge":
        rows.append([InlineKeyboardButton("Расписание челленджа", callback_data="schedule_challenge")])
    await update.effective_message.reply_text(
        "Тут ты можешь настроить свое расписание, изменить время или приостановить рассылку.",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "schedule_time":
        from app.daily.set_time import handle_set_time_callback
        await handle_set_time_callback(update, context)
    elif query.data == "schedule_pause":
        from app.daily.pause import pause_toggle_command
        await pause_toggle_command(update, context)
    elif query.data == "schedule_challenge":
        if get_user_bot_mode(update.effective_user.id) != "challenge":
            await query.answer("Расписание доступно только участникам челленджа.", show_alert=True)
            return
        await query.answer()
        text = get_last_published_challenge_schedule(update.effective_user.id)
        if text is None:
            await update.effective_message.reply_text("Расписание челленджа пока не опубликовано.")
            return
        await update.effective_message.reply_text(text, parse_mode="Markdown")
