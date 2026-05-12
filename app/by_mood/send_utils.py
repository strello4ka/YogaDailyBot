"""Отправка одной практики в режиме By mood (формат сообщения + кнопка «Я сделал»)."""

import logging

from telegram.ext import ContextTypes

from app.keyboards import get_practice_done_keyboard
from data.db import (
    BY_MOOD_PRACTICE_LOG_DAY,
    get_last_practice_message_id,
    increment_total_practices,
    log_practice_sent,
    record_by_mood_seen,
    set_last_practice_message_id,
    set_user_blocked,
)

logger = logging.getLogger(__name__)


def format_by_mood_practice_message(
    my_description: str,
    time_practices: int,
    intensity: str,
    channel_name: str,
    video_url: str,
) -> str:
    parts = ["*Практика для тебя*\n"]
    if my_description:
        parts.append(my_description)
    else:
        parts.append("Новая практика ждёт тебя!")
    parts.append(f"\n🌀 *время:* {time_practices} мин")
    if intensity:
        parts.append(f"🌀 *интенсивность:* {intensity}")
    parts.append(f"🌀 *канал:* {channel_name}")
    parts.append(f"\n▶️ [Youtube]({video_url})")
    return "\n".join(parts)


async def deliver_by_mood_practice(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    filter_key: str,
    practice_row: tuple,
) -> bool:
    """practice_row — кортеж как из pick_random_by_mood_practice."""
    (
        practice_id,
        _title,
        video_url,
        time_practices,
        channel_name,
        _description,
        my_description,
        intensity,
        _weekday,
        _created_at,
        _updated_at,
    ) = practice_row

    try:
        last_message_id = get_last_practice_message_id(user_id)
        if last_message_id is not None:
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=last_message_id, reply_markup=None
                )
            except Exception as edit_err:
                logger.debug("Не удалось снять кнопку с прошлого сообщения: %s", edit_err)

        record_by_mood_seen(user_id, filter_key, practice_id)

        text = format_by_mood_practice_message(
            my_description or "",
            time_practices,
            intensity or "",
            channel_name,
            video_url,
        )
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            disable_web_page_preview=False,
            reply_markup=get_practice_done_keyboard(),
        )
        set_last_practice_message_id(user_id, msg.message_id)
        set_user_blocked(user_id, False)
        increment_total_practices(user_id)
        log_practice_sent(user_id, practice_id, BY_MOOD_PRACTICE_LOG_DAY)
        return True
    except Exception as e:
        err = str(e)
        if "bot was blocked by the user" in err or "Forbidden: bot was blocked by the user" in err:
            set_user_blocked(user_id, True)
        logger.error("Ошибка deliver_by_mood_practice user=%s: %s", user_id, e)
        return False
