"""Блокировка и разблокировка бота: запись is_blocked в базу.

Два канала:
1) событие Telegram my_chat_member (пользователь нажал Block/Unblock);
2) ошибка отправки «bot was blocked by the user» — подстраховка, если событие не дошло.
"""

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

from data.db import clear_user_blocked_if_needed, set_user_blocked

logger = logging.getLogger(__name__)


async def clear_stale_block_on_private_activity(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Снимает устаревший флаг блокировки при активности в личном чате.

    Заблокированный пользователь не может отправить боту сообщение, команду или
    callback. Поэтому любое такое входящее действие надёжно подтверждает, что
    бот уже разблокирован, даже если событие my_chat_member было потеряно.
    """
    chat = update.effective_chat
    user = update.effective_user
    is_user_activity = update.message is not None or update.callback_query is not None
    if (
        not chat
        or chat.type != ChatType.PRIVATE
        or not user
        or user.is_bot
        or not is_user_activity
    ):
        return

    # Системная кнопка Start появляется в Telegram после разблокировки. Этот
    # случай синхронно разбирает start_command, чтобы не возникла гонка с
    # обычным сценарием подтверждения полного перезапуска.
    if update.message and (update.message.text or "").split(maxsplit=1)[0].split("@", 1)[0] == "/start":
        return

    # Подключение к удалённой БД синхронное, поэтому не задерживаем основной
    # обработчик сообщения / callback пользователя.
    changed = await asyncio.to_thread(clear_user_blocked_if_needed, user.id)
    if changed:
        logger.info(
            "Снят устаревший is_blocked по входящей активности user=%s",
            user.id,
        )


def is_bot_blocked_error(error: BaseException) -> bool:
    """True, если Telegram вернул, что пользователь заблокировал бота."""
    return "blocked by the user" in str(error).lower()


def mark_blocked_if_forbidden(user_id: int, error: BaseException) -> bool:
    """При Forbidden/blocked помечает пользователя is_blocked=True.

    Returns:
        True, если это ошибка блокировки и флаг проставлен (или уже пытались проставить).
    """
    if not is_bot_blocked_error(error):
        return False
    set_user_blocked(user_id, True)
    logger.info(
        "Пользователь %s заблокировал бота (ошибка отправки), is_blocked=True",
        user_id,
    )
    return True


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

    if new_status == ChatMemberStatus.BANNED:
        context.user_data.pop("just_unblocked", None)
        set_user_blocked(user_id, True)
        logger.info("Пользователь %s заблокировал бота", user_id)
        return

    if new_status == ChatMemberStatus.MEMBER:
        set_user_blocked(user_id, False)
        context.user_data["just_unblocked"] = True
        logger.info("Пользователь %s разблокировал бота", user_id)
