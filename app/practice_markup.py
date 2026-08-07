"""Снятие «✅ Я сделал!» с сохранением постоянных действий практики."""

import logging
from typing import Optional

from telegram import InlineKeyboardMarkup

from app.keyboards import get_practice_favorite_keyboard, practice_id_from_action_markup
from app.practice_ref import practice_catalog_from_action_markup
from data.db import (
    PRACTICE_CATALOG_YOGA,
    get_last_practice_catalog,
    get_last_practice_id,
    is_user_favorite,
)

logger = logging.getLogger(__name__)


async def keep_favorite_button_on_message(
    bot,
    chat_id: int,
    message_id: int,
    user_id: int,
    *,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    practice_id: Optional[int] = None,
    practice_catalog: Optional[str] = None,
) -> None:
    """Убирает «✅ Я сделал!», оставляет реакции и избранное."""
    pid = practice_id or practice_id_from_action_markup(reply_markup)
    catalog = practice_catalog or practice_catalog_from_action_markup(reply_markup)
    if pid is None:
        pid = get_last_practice_id(user_id)
        catalog = get_last_practice_catalog(user_id)
    if catalog is None:
        catalog = PRACTICE_CATALOG_YOGA
    if pid is None:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception as e:
            logger.debug("keep_favorite: снять клавиатуру msg=%s: %s", message_id, e)
        return

    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=get_practice_favorite_keyboard(
                pid, is_user_favorite(user_id, pid, catalog), catalog
            ),
        )
    except Exception as e:
        logger.debug("keep_favorite: обновить клавиатуру msg=%s: %s", message_id, e)
