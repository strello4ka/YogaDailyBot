"""Общий учёт действий пользователя для напоминаний о неактивности."""

import asyncio

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from data.db import touch_user_activity_for_inactivity_reminders


async def record_private_user_activity(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Сбрасывает срок неактивности при любом действии пользователя в личке."""
    chat = update.effective_chat
    user = update.effective_user
    is_user_action = update.message is not None or update.callback_query is not None
    if (
        not chat
        or chat.type != ChatType.PRIVATE
        or not user
        or user.is_bot
        or not is_user_action
    ):
        return

    # PostgreSQL-клиент синхронный; не задерживаем остальные обработчики update.
    await asyncio.to_thread(touch_user_activity_for_inactivity_reminders, user.id)
