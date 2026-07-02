"""Избранные практики: /favorite, переключатель под практикой, выдача из списка."""

import logging
import math
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.by_mood.send_utils import deliver_on_demand_practice
from app.keyboards import get_practice_action_keyboard
from data.db import (
    add_user_favorite,
    get_yoga_practice_by_id,
    is_user_favorite,
    list_user_favorites,
    remove_user_favorite,
)

logger = logging.getLogger(__name__)

FAVORITES_PAGE_SIZE = 6
TELEGRAM_BUTTON_TEXT_LIMIT = 64

EMPTY_FAVORITES_TEXT = (
    "У тебя пока нет избранных практик.\n"
    "Нажми «🧡 В избранное» под любой понравившейся практикой, и она появится здесь."
)

FAVORITES_ADD_ALERT = (
    "Добавил практику в избранное 🧡\n"
    "Ищи этот раздел в меню ↙️"
)
FAVORITES_REMOVE_TOAST = "Удалил практику из избранного"


def format_favorite_list_button_label(channel_name: str, title: str, time_practices: int) -> str:
    """Формат: {канал} · {название} {N} мин (с обрезкой под лимит Telegram)."""
    channel = (channel_name or "").strip() or "Канал"
    name = (title or "").strip() or "Практика"
    suffix = f" {time_practices} мин"
    prefix = f"{channel} · {name}"
    label = f"{prefix}{suffix}"
    if len(label) <= TELEGRAM_BUTTON_TEXT_LIMIT:
        return label

    fixed = f"{channel} · "
    end = suffix
    available = TELEGRAM_BUTTON_TEXT_LIMIT - len(fixed) - len(end) - 1
    if available < 1:
        return label[: TELEGRAM_BUTTON_TEXT_LIMIT - 1] + "…"
    truncated = name[:available] + ("…" if len(name) > available else "")
    return f"{fixed}{truncated}{end}"


def _favorites_list_keyboard(favorites: list, page: int) -> Optional[InlineKeyboardMarkup]:
    total = len(favorites)
    if total == 0:
        return None

    total_pages = max(1, math.ceil(total / FAVORITES_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    start = page * FAVORITES_PAGE_SIZE
    chunk = favorites[start : start + FAVORITES_PAGE_SIZE]

    rows = []
    for row in chunk:
        practice_id, title, *_rest = row
        time_practices = row[3]
        channel_name = row[4]
        label = format_favorite_list_button_label(channel_name, title, time_practices)
        rows.append([InlineKeyboardButton(label, callback_data=f"fav_pick:{practice_id}")])

    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"fav_page:{page - 1}"))
        nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="fav_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"fav_page:{page + 1}"))
        rows.append(nav)

    return InlineKeyboardMarkup(rows)


def _favorites_list_text(favorites: list) -> str:
    if not favorites:
        return EMPTY_FAVORITES_TEXT
    return "🧡 Твои любимки"


async def _send_favorites_list(
    *,
    bot,
    chat_id: int,
    user_id: int,
    page: int = 0,
    message_id: Optional[int] = None,
) -> None:
    favorites = list_user_favorites(user_id)
    text = _favorites_list_text(favorites)
    reply_markup = _favorites_list_keyboard(favorites, page)

    if message_id is not None:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    else:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def favorite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return
    await _send_favorites_list(bot=context.bot, chat_id=chat.id, user_id=user.id, page=0)


async def handle_fav_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    user = update.effective_user
    if not user:
        await query.answer("Ошибка.")
        return

    try:
        practice_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer("Ошибка.")
        return

    if not get_yoga_practice_by_id(practice_id):
        await query.answer("Практика больше не доступна.")
        return

    if is_user_favorite(user.id, practice_id):
        remove_user_favorite(user.id, practice_id)
        await query.answer(FAVORITES_REMOVE_TOAST)
        is_fav = False
    else:
        add_user_favorite(user.id, practice_id)
        await query.answer(FAVORITES_ADD_ALERT, show_alert=True)
        is_fav = True

    try:
        await query.edit_message_reply_markup(
            reply_markup=get_practice_action_keyboard(practice_id, is_fav),
        )
    except Exception as e:
        logger.debug("Не удалось обновить клавиатуру избранного: %s", e)


async def handle_fav_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return

    user = update.effective_user
    if not user:
        await query.answer()
        return

    try:
        page = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer()
        return

    await query.answer()
    await _send_favorites_list(
        bot=context.bot,
        chat_id=query.message.chat_id,
        user_id=user.id,
        page=page,
        message_id=query.message.message_id,
    )


async def handle_fav_noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()


async def handle_fav_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        await query.answer("Ошибка.")
        return

    try:
        practice_id = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer("Ошибка.")
        return

    practice = get_yoga_practice_by_id(practice_id)
    if not practice:
        await query.answer("Практика больше не доступна.")
        return

    await query.answer()
    ok = await deliver_on_demand_practice(
        context, chat.id, user.id, practice, touch_activity=False
    )
    if not ok:
        await context.bot.send_message(chat.id, "Не удалось отправить практику. Попробуй ещё раз.")
