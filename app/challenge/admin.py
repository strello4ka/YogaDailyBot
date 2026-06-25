"""Админ-команды для утренней сводки челленджа в групповой чат."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.secret import ADMIN_USER_ID
from app.challenge.job import send_challenge_group_summary
from data.db import reset_challenge_summary_state

logger = logging.getLogger(__name__)


async def challenge_summary_preview_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сводку сразу (без ожидания 10:10), не меняя флаги отправки."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    ok = await send_challenge_group_summary(context, force=True)
    if ok:
        await update.message.reply_text("✅ Превью сводки отправлено в групповой чат.")
    else:
        await update.message.reply_text(
            "❌ Не удалось отправить сводку. Проверь CHALLENGE_GROUP_CHAT_ID, участников челленджа и логи."
        )


async def challenge_summary_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает флаги остановки и последней отправки для нового потока челленджа."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    if reset_challenge_summary_state():
        await update.message.reply_text("✅ Состояние утренней сводки сброшено. Рассылка снова активна.")
        logger.info("Админ %s сбросил состояние сводки челленджа", user_id)
    else:
        await update.message.reply_text("❌ Не удалось сбросить состояние сводки.")
