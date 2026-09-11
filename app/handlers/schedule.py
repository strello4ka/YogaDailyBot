"""Temporary menu placeholder; onboarding scheduling remains functional."""

from telegram import Update
from telegram.ext import ContextTypes


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("🕐 Раздел «Расписание» скоро появится.")
