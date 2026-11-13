"""MVP breathing practice rendered inside a Telegram message widget."""

import logging
from pathlib import Path

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def breathing_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the local breathing widget to a private chat."""
    chat = update.effective_chat
    message = update.effective_message
    if not chat or chat.type != "private" or not message:
        return

    html = Path(__file__).with_name("breathing_widget.html").read_text(encoding="utf-8")
    payload = {"chat_id": chat.id, "html": html, "caption": "Дыхательная практика"}
    if message.is_topic_message and message.message_thread_id:
        payload["message_thread_id"] = message.message_thread_id
    try:
        await context.bot._post("sendWidget", payload)
    except TelegramError as exc:
        logger.warning("Breathing widget send failed: %s", exc)
        await message.reply_text(
            "Telegram не смог открыть дыхательный виджет. Попробуй ещё раз чуть позже."
        )
