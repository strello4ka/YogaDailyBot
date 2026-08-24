"""Дополнительные практики по логике By mood без смены режима Daily/Challenge.

Reply-кнопка «Еще практики» остаётся на основной клавиатуре; фильтры — inline под
отдельным сообщением (callback_data с префиксом extra_mood / extra_self_*).
"""

from __future__ import annotations

import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.by_mood.quick_filters import (
    get_active_quick_filters,
    record_quick_filter_click,
    select_and_deliver_quick_filter,
)
from app.by_mood.self_decide import time_keyboard
from app.by_mood.self_decide import handle_difficulty_callback as self_handle_difficulty
from app.by_mood.self_decide import handle_teg_callback as self_handle_teg
from app.by_mood.self_decide import handle_time_callback as self_handle_time
from data.db import (
    append_extra_practices_inline_message,
    get_user_bot_mode,
    remove_extra_practices_inline_message,
    take_and_clear_extra_practices_inline_messages,
)

logger = logging.getLogger(__name__)

EXTRA_PRACTICES_INTRO = (
    "Тут ты можешь получить дополнительные практики отдельно от ежедневной рассылки.\n"
    "Выбери, что тебе хочется сейчас, по кнопкам ниже.\n\n"
    "Если хочешь отменить ежедневную рассылку и получать только практики по кнопкам, "
    "измени режим в меню на By mood"
)

EXTRA_MOOD_PREFIX = "extra_mood:"
EXTRA_SELF_TIME_PREFIX = "extra_self_time"
EXTRA_SELF_TEG_PREFIX = "extra_self_teg"
EXTRA_SELF_DIFFICULTY_PREFIX = "extra_self_difficulty"

_STALE_EXTRA_MSG = (
    "Эти кнопки доступны в режимах Daily или Challenge. Выбери режим через /change_mode."
)

def get_extra_practices_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            spec.label,
            callback_data=f"{EXTRA_MOOD_PREFIX}{spec.slug}",
        )
        for spec in get_active_quick_filters()
    ]
    return InlineKeyboardMarkup(
        [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    )


async def send_extra_practices_intro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text(
        EXTRA_PRACTICES_INTRO,
        reply_markup=get_extra_practices_inline_keyboard(),
    )
    user = update.effective_user
    chat = update.effective_chat
    if user and chat:
        append_extra_practices_inline_message(user.id, chat.id, msg.message_id)


async def strip_extra_practices_inline_keyboards(bot, user_id: int) -> None:
    """Снимает inline с всех отслеживаемых сообщений «Еще практики» (например после смены режима)."""
    pairs = take_and_clear_extra_practices_inline_messages(user_id)
    for pair in pairs:
        if len(pair) < 2:
            continue
        chat_id, message_id = int(pair[0]), int(pair[1])
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception as e:
            logger.debug(
                "Не удалось снять inline «Еще практики» chat=%s msg=%s: %s",
                chat_id,
                message_id,
                e,
            )


def user_may_use_extra_practices(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    return get_user_bot_mode(user_id) in ("daily", "challenge")


async def handle_extra_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline: extra_mood:* — фильтры как в By mood, режим не меняется."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or not user_may_use_extra_practices(user.id):
        await query.edit_message_reply_markup(reply_markup=None)
        if user and chat and query.message:
            remove_extra_practices_inline_message(user.id, chat.id, query.message.message_id)
        await query.message.reply_text(_STALE_EXTRA_MSG)
        return

    data = query.data or ""
    if not data.startswith(EXTRA_MOOD_PREFIX):
        return
    slug = data[len(EXTRA_MOOD_PREFIX) :]
    if slug == "self_start":  # Совместимость с уже отправленными старыми кнопками.
        slug = "self"

    active_filters = {spec.slug: spec for spec in get_active_quick_filters()}
    spec = active_filters.get(slug)
    if not spec:
        await query.message.reply_text("Эта быстрая кнопка сейчас выключена.")
        return

    if spec.pool == "flow":
        record_quick_filter_click(user.id, spec, "extra", None)
        msg = await query.message.reply_text(
            "Настрой свою практику *сам*:\nсначала выбери время (в минутах)👇",
            parse_mode="Markdown",
            reply_markup=time_keyboard(callback_prefix=EXTRA_SELF_TIME_PREFIX),
        )
        append_extra_practices_inline_message(user.id, chat.id, msg.message_id)
        return

    result = await select_and_deliver_quick_filter(
        context,
        user.id,
        chat.id,
        spec,
        "extra",
    )
    if result == "empty":
        await query.message.reply_text(spec.empty_message)
    elif result == "failed":
        await query.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")


async def handle_extra_self_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not user_may_use_extra_practices(user.id):
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_reply_markup(reply_markup=None)
            if user and update.effective_chat and query.message:
                remove_extra_practices_inline_message(
                    user.id, update.effective_chat.id, query.message.message_id
                )
            await query.message.reply_text(_STALE_EXTRA_MSG)
        return
    await self_handle_time(
        update,
        context,
        time_callback_prefix=EXTRA_SELF_TIME_PREFIX,
        teg_callback_prefix=EXTRA_SELF_TEG_PREFIX,
    )


async def handle_extra_self_teg_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not user or not user_may_use_extra_practices(user.id):
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_reply_markup(reply_markup=None)
            if user and update.effective_chat and query.message:
                remove_extra_practices_inline_message(
                    user.id, update.effective_chat.id, query.message.message_id
                )
            await query.message.reply_text(_STALE_EXTRA_MSG)
        return
    await self_handle_teg(
        update,
        context,
        time_callback_prefix=EXTRA_SELF_TIME_PREFIX,
        teg_callback_prefix=EXTRA_SELF_TEG_PREFIX,
        difficulty_callback_prefix=EXTRA_SELF_DIFFICULTY_PREFIX,
    )


async def handle_extra_self_difficulty_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not user or not user_may_use_extra_practices(user.id):
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_reply_markup(reply_markup=None)
            if user and update.effective_chat and query.message:
                remove_extra_practices_inline_message(
                    user.id, update.effective_chat.id, query.message.message_id
                )
            await query.message.reply_text(_STALE_EXTRA_MSG)
        return
    await self_handle_difficulty(
        update, context, difficulty_callback_prefix=EXTRA_SELF_DIFFICULTY_PREFIX
    )
