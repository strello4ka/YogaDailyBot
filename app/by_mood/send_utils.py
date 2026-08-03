"""Отправка одной практики в режиме By mood (формат сообщения + кнопка «✅ Я сделал!»)."""

import logging
from typing import Optional

from telegram.ext import ContextTypes

from app.keyboards import get_practice_action_keyboard
from app.block import mark_blocked_if_forbidden
from data.db import (
    BY_MOOD_PRACTICE_LOG_DAY,
    split_practice_row_with_catalog,
    increment_total_practices,
    is_user_favorite,
    log_practice_sent,
    record_by_mood_seen,
    set_last_practice_message_id,
    touch_by_mood_activity,
)

logger = logging.getLogger(__name__)


def format_by_mood_practice_message(
    my_description: str,
    time_practices: int,
    difficulty: str,
    channel_name: str,
    video_url: str,
) -> str:
    parts = ["*Практика для тебя*\n"]
    if my_description:
        parts.append(my_description)
    else:
        parts.append("Новая практика ждёт тебя!")
    parts.append(f"\n🌀 *время:* {time_practices} мин")
    if difficulty:
        parts.append(f"🌀 *сложность:* {difficulty}")
    parts.append(f"🌀 *канал:* {channel_name}")
    parts.append(f"\n▶️ [Youtube]({video_url})")
    return "\n".join(parts)


async def deliver_on_demand_practice(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    practice_row: tuple,
    *,
    record_seen_filter_key: Optional[str] = None,
    touch_activity: bool = True,
) -> bool:
    """Отправляет практику по запросу (By mood, избранное и т.п.)."""
    practice_row, practice_catalog = split_practice_row_with_catalog(practice_row)
    (
        practice_id,
        _title,
        video_url,
        time_practices,
        channel_name,
        _description,
        my_description,
        difficulty,
        _weekday,
        _created_at,
        _updated_at,
    ) = practice_row

    try:
        from app.handlers.done import strip_previous_day_done_button

        await strip_previous_day_done_button(context.bot, chat_id, user_id)

        if record_seen_filter_key:
            record_by_mood_seen(
                user_id, record_seen_filter_key, practice_id, practice_catalog
            )

        text = format_by_mood_practice_message(
            my_description or "",
            time_practices,
            difficulty or "",
            channel_name,
            video_url,
        )
        is_fav = is_user_favorite(user_id, practice_id, practice_catalog)
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            disable_web_page_preview=False,
            reply_markup=get_practice_action_keyboard(
                practice_id, is_fav, practice_catalog
            ),
        )
        set_last_practice_message_id(
            user_id, msg.message_id, practice_id, practice_catalog
        )
        increment_total_practices(user_id)
        if touch_activity:
            touch_by_mood_activity(user_id)
        log_id = log_practice_sent(
            user_id,
            practice_id,
            BY_MOOD_PRACTICE_LOG_DAY,
            practice_catalog,
            chat_id=chat_id,
            message_id=msg.message_id,
        )
        if log_id:
            from app.handlers.done import schedule_done_reminders

            await schedule_done_reminders(context, chat_id, user_id, log_id)
        return True
    except Exception as e:
        if not mark_blocked_if_forbidden(user_id, e):
            logger.error("Ошибка deliver_on_demand_practice user=%s: %s", user_id, e)
        return False


async def deliver_by_mood_practice(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    filter_key: str,
    practice_row: tuple,
) -> bool:
    """practice_row — кортеж из pick_random_* (11 полей + practice_catalog)."""
    return await deliver_on_demand_practice(
        context,
        chat_id,
        user_id,
        practice_row,
        record_seen_filter_key=filter_key,
        touch_activity=True,
    )
