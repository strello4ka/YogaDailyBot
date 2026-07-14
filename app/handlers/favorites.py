"""Избранные практики: /favorite (карусель), переключатель под практикой."""

import logging
from typing import Optional

from telegram import InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.keyboards import (
    get_favorites_carousel_keyboard,
    get_practice_action_keyboard,
    get_practice_favorite_keyboard,
    message_has_done_button,
)
from app.practice_ref import parse_practice_callback
from data.db import (
    PRACTICE_CATALOG_YOGA,
    add_user_favorite,
    get_practice_by_catalog,
    is_user_favorite,
    list_user_favorites,
    remove_user_favorite,
)

logger = logging.getLogger(__name__)

EMPTY_FAVORITES_TEXT = (
    "У тебя пока нет избранных практик.\n"
    "Нажми «🧡 В избранное» под любой понравившейся практикой, и она появится здесь."
)

FAVORITES_ADD_TOAST = (
    "Добавил практику в избранное 🧡\n"
)
FAVORITES_REMOVE_TOAST = "Удалил практику из избранного"


def format_favorite_carousel_message(practice_row: tuple) -> str:
    """Текст карточки практики в карусели избранного: title + метаданные."""
    row = practice_row[:11]
    (
        _practice_id,
        title,
        video_url,
        time_practices,
        channel_name,
        _description,
        _my_description,
        intensity,
        _weekday,
        _created_at,
        _updated_at,
    ) = row

    parts = [f"*{title}*" if title else "*Практика для тебя*", ""]
    parts.append(f"🌀 *время:* {time_practices} мин")
    if intensity:
        parts.append(f"🌀 *интенсивность:* {intensity}")
    parts.append(f"🌀 *канал:* {channel_name}")
    parts.append(f"\n▶️ [Youtube]({video_url})")
    return "\n".join(parts)


def _clamp_carousel_index(index: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(index, total - 1))


def _index_of_practice(favorites: list, practice_id: int, practice_catalog: str) -> int:
    for i, row in enumerate(favorites):
        if row[0] == practice_id and row[11] == practice_catalog:
            return i
    return 0


def message_is_favorites_carousel(reply_markup: Optional[InlineKeyboardMarkup]) -> bool:
    if not reply_markup or not reply_markup.inline_keyboard:
        return False
    for row in reply_markup.inline_keyboard:
        for btn in row:
            data = btn.callback_data or ""
            if data.startswith("fav_nav:"):
                return True
    return False


def get_carousel_index_from_markup(reply_markup: Optional[InlineKeyboardMarkup]) -> int:
    if not reply_markup:
        return 0
    for row in reply_markup.inline_keyboard:
        for btn in row:
            if btn.callback_data == "fav_noop" and btn.text and " / " in btn.text:
                try:
                    return int(btn.text.split(" / ")[0].strip()) - 1
                except ValueError:
                    return 0
    return 0


async def render_favorites_carousel(
    *,
    bot,
    chat_id: int,
    user_id: int,
    index: int = 0,
    message_id: Optional[int] = None,
) -> None:
    favorites = list_user_favorites(user_id)
    if not favorites:
        if message_id is not None:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=EMPTY_FAVORITES_TEXT,
                reply_markup=None,
            )
        else:
            await bot.send_message(chat_id=chat_id, text=EMPTY_FAVORITES_TEXT)
        return

    total = len(favorites)
    index = _clamp_carousel_index(index, total)
    practice = favorites[index]
    practice_id = practice[0]
    practice_catalog = practice[11] if len(practice) > 11 else PRACTICE_CATALOG_YOGA
    text = format_favorite_carousel_message(practice)
    reply_markup = get_favorites_carousel_keyboard(
        practice_id,
        is_user_favorite(user_id, practice_id, practice_catalog),
        index,
        total,
        practice_catalog,
    )

    if message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=False,
                reply_markup=reply_markup,
            )
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            disable_web_page_preview=False,
            reply_markup=reply_markup,
        )


async def favorite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    await render_favorites_carousel(
        bot=context.bot,
        chat_id=chat.id,
        user_id=user.id,
        index=0,
    )


async def handle_fav_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    user = update.effective_user
    if not user:
        await query.answer("Ошибка.")
        return

    practice_id, practice_catalog = parse_practice_callback(query.data, "fav_toggle")
    if practice_id is None:
        await query.answer("Ошибка.")
        return

    if not get_practice_by_catalog(practice_id, practice_catalog):
        await query.answer("Практика больше не доступна.")
        return

    is_carousel = message_is_favorites_carousel(
        query.message.reply_markup if query.message else None
    )
    carousel_index = 0
    if is_carousel:
        favorites = list_user_favorites(user.id)
        carousel_index = _index_of_practice(favorites, practice_id, practice_catalog)

    if is_user_favorite(user.id, practice_id, practice_catalog):
        remove_user_favorite(user.id, practice_id, practice_catalog)
        await query.answer(FAVORITES_REMOVE_TOAST)
    else:
        add_user_favorite(user.id, practice_id, practice_catalog)
        await query.answer(FAVORITES_ADD_TOAST)

    if is_carousel and query.message:
        favorites = list_user_favorites(user.id)
        if not favorites:
            await render_favorites_carousel(
                bot=context.bot,
                chat_id=query.message.chat_id,
                user_id=user.id,
                index=0,
                message_id=query.message.message_id,
            )
        else:
            await render_favorites_carousel(
                bot=context.bot,
                chat_id=query.message.chat_id,
                user_id=user.id,
                index=_clamp_carousel_index(carousel_index, len(favorites)),
                message_id=query.message.message_id,
            )
        return

    is_fav = is_user_favorite(user.id, practice_id, practice_catalog)
    markup = query.message.reply_markup if query.message else None
    keyboard_fn = (
        get_practice_action_keyboard
        if message_has_done_button(markup)
        else get_practice_favorite_keyboard
    )
    try:
        await query.edit_message_reply_markup(
            reply_markup=keyboard_fn(practice_id, is_fav, practice_catalog),
        )
    except Exception as e:
        logger.debug("Не удалось обновить клавиатуру избранного: %s", e)


async def handle_fav_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return

    user = update.effective_user
    if not user:
        await query.answer()
        return

    try:
        index = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer()
        return

    await query.answer()
    await render_favorites_carousel(
        bot=context.bot,
        chat_id=query.message.chat_id,
        user_id=user.id,
        index=index,
        message_id=query.message.message_id,
    )


async def handle_fav_noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
