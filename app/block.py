"""Блокировка и разблокировка бота: запись is_blocked в базу по событию от Telegram."""

import logging

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

from data.db import set_user_blocked

logger = logging.getLogger(__name__)


async def handle_user_block_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пользователь заблокировал или разблокировал бота — обновляем флаг в базе."""
    event = update.my_chat_member
    if not event or event.chat.type != ChatType.PRIVATE:
        return

    new_member = event.new_chat_member
    if not new_member.user.is_bot:
        return

    user_id = event.chat.id
    new_status = new_member.status

    if new_status == ChatMemberStatus.KICKED:
        set_user_blocked(user_id, True)
        logger.info("Пользователь %s заблокировал бота", user_id)
        return

    if new_status == ChatMemberStatus.MEMBER:
        set_user_blocked(user_id, False)
        logger.info("Пользователь %s разблокировал бота", user_id)
