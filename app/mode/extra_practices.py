"""Дополнительные практики по логике By mood без смены режима Daily/Challenge.

Reply-кнопка «Еще практики» остаётся на основной клавиатуре; фильтры — inline под
отдельным сообщением (callback_data с префиксом extra_mood / extra_self_*).
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.by_mood import five_min, hard, lazy_days, no_mat, practice_of_day
from app.by_mood.self_decide import time_keyboard
from app.by_mood.self_decide import handle_intensity_callback as self_handle_intensity
from app.by_mood.self_decide import handle_time_callback as self_handle_time
from app.by_mood.send_utils import deliver_by_mood_practice
from data.db import (
    append_extra_practices_inline_message,
    get_user_bot_mode,
    pick_random_by_mood_practice,
    remove_extra_practices_inline_message,
    take_and_clear_extra_practices_inline_messages,
)

logger = logging.getLogger(__name__)

EXTRA_PRACTICES_INTRO = (
    "Тут ты можешь получить дополнительные практики отдельно от ежедневной рассылки.\n"
    "Выбери, что тебе хочется сейчас, по кнопкам ниже.\n\n"
    "Если хочешь полностью отменить ежедневную рассылку и получать только практики по кнопкам, "
    "измени режим в меню"
)

EXTRA_MOOD_PREFIX = "extra_mood:"
EXTRA_SELF_TIME_PREFIX = "extra_self_time"
EXTRA_SELF_INTENSITY_PREFIX = "extra_self_intensity"

_STALE_EXTRA_MSG = (
    "Эти кнопки доступны в режимах Daily или Challenge. Выбери режим через /change_mode."
)

# (callback_slug, filter_key, where_sql, params, сообщение если пусто)
_EXTRA_FILTER_ROWS: tuple[tuple[str, str, str, tuple, str], ...] = (
    (
        "day",
        practice_of_day.FILTER_KEY,
        "",
        (),
        "Сейчас не нашлось подходящей практики в базе. Попробуй чуть позже или другой фильтр.",
    ),
    (
        "no_mat",
        no_mat.FILTER_KEY,
        no_mat.WHERE,
        (),
        "Пока нет практик с отметкой «без коврика» в базе. Как только добавим — фильтр заработает.",
    ),
    (
        "lazy",
        lazy_days.FILTER_KEY,
        lazy_days.WHERE,
        (),
        "Не нашлось практик с очень низкой интенсивностью. Попробуй другой фильтр.",
    ),
    (
        "five",
        five_min.FILTER_KEY,
        five_min.WHERE,
        (),
        "Не нашлось коротких практик до 8 минут включительно. Попробуй другой фильтр.",
    ),
    (
        "hard",
        hard.FILTER_KEY,
        hard.WHERE,
        (),
        "Не нашлось практик со сверх высокой интенсивностью. Попробуй другой фильтр.",
    ),
)

_EXTRA_SLUG_MAP = {row[0]: row for row in _EXTRA_FILTER_ROWS}


def get_extra_practices_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Практика дня", callback_data=f"{EXTRA_MOOD_PREFIX}day"),
                InlineKeyboardButton("Без коврика", callback_data=f"{EXTRA_MOOD_PREFIX}no_mat"),
            ],
            [
                InlineKeyboardButton("Ленивые дни", callback_data=f"{EXTRA_MOOD_PREFIX}lazy"),
                InlineKeyboardButton("Пятиминутка", callback_data=f"{EXTRA_MOOD_PREFIX}five"),
            ],
            [
                InlineKeyboardButton("Хард", callback_data=f"{EXTRA_MOOD_PREFIX}hard"),
                InlineKeyboardButton("Сам решу", callback_data=f"{EXTRA_MOOD_PREFIX}self_start"),
            ],
        ]
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


def user_may_use_extra_practices(user_id: int | None) -> bool:
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
        remove_extra_practices_inline_message(user.id, chat.id, query.message.message_id)
        await query.message.reply_text(_STALE_EXTRA_MSG)
        return

    data = query.data or ""
    if not data.startswith(EXTRA_MOOD_PREFIX):
        return
    slug = data[len(EXTRA_MOOD_PREFIX) :]

    if slug == "self_start":
        await query.edit_message_text(
            "Настрой свою практику *сам*:\nсначала выбери время (в минутах)👇",
            parse_mode="Markdown",
            reply_markup=time_keyboard(callback_prefix=EXTRA_SELF_TIME_PREFIX),
        )
        return

    spec = _EXTRA_SLUG_MAP.get(slug)
    if not spec:
        await query.message.reply_text("Что-то пошло не так. Нажми «Еще практики» ещё раз.")
        return

    _cb_slug, filter_key, where_sql, params, empty_msg = spec
    row = pick_random_by_mood_practice(user.id, filter_key, where_sql, params)
    if not row:
        await query.message.reply_text(empty_msg)
        return

    await query.edit_message_reply_markup(reply_markup=None)
    remove_extra_practices_inline_message(user.id, chat.id, query.message.message_id)
    ok = await deliver_by_mood_practice(context, chat.id, user.id, filter_key, row)
    if not ok:
        await query.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")


async def handle_extra_self_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not user_may_use_extra_practices(user.id):
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_reply_markup(reply_markup=None)
            remove_extra_practices_inline_message(
                user.id, update.effective_chat.id, query.message.message_id
            )
            await query.message.reply_text(_STALE_EXTRA_MSG)
        return
    await self_handle_time(
        update,
        context,
        time_callback_prefix=EXTRA_SELF_TIME_PREFIX,
        intensity_callback_prefix=EXTRA_SELF_INTENSITY_PREFIX,
    )


async def handle_extra_self_intensity_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    if not user or not user_may_use_extra_practices(user.id):
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_reply_markup(reply_markup=None)
            remove_extra_practices_inline_message(
                user.id, update.effective_chat.id, query.message.message_id
            )
            await query.message.reply_text(_STALE_EXTRA_MSG)
        return
    await self_handle_intensity(
        update, context, intensity_callback_prefix=EXTRA_SELF_INTENSITY_PREFIX
    )
