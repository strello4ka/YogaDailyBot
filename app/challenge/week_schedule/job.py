"""Автоотправка воскресного расписания челленджа (вс 20:00 МСК)."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from app.config import CHALLENGE_GROUP_CHAT_ID, DEFAULT_TZ
from app.challenge.cohort import (
    SCHEDULE_HOUR,
    SCHEDULE_MINUTE,
    get_upcoming_week_day_range,
)
from app.challenge.week_schedule.messages import build_weekly_schedule_message
from data.db import (
    get_group_challenge_day,
    get_group_challenge_start_id,
    get_yoga_practice_by_challenge_order,
    is_challenge_summary_stopped,
    is_challenge_weekly_schedule_sent_on,
    mark_challenge_weekly_schedule_sent,
)

logger = logging.getLogger(__name__)
MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)


def _now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _is_schedule_time(now: datetime) -> bool:
    local = now.astimezone(MOSCOW_TZ)
    return (
        local.weekday() == 6
        and local.hour == SCHEDULE_HOUR
        and local.minute == SCHEDULE_MINUTE
    )


def _load_week_practices(challenge_start_id: int, from_day: int, to_day: int) -> list[tuple[int, str, str, int]]:
    practices: list[tuple[int, str, str, int]] = []
    for day in range(from_day, to_day + 1):
        row = get_yoga_practice_by_challenge_order(challenge_start_id, day)
        if not row:
            logger.warning("Практика для дня %s не найдена (start_id=%s)", day, challenge_start_id)
            continue
        title = (row[1] or "Практика").strip()
        channel_name = (row[4] or "—").strip()
        minutes = int(row[3]) if row[3] is not None else 0
        practices.append((day, title, channel_name, minutes))
    return practices


async def send_challenge_weekly_schedule(context: ContextTypes.DEFAULT_TYPE, *, force: bool = False) -> bool:
    """Отправляет расписание на неделю в групповой чат.

    force=True — без проверки времени (preview).
    Участники challenge не обязательны: достаточно env потока и CHALLENGE_GROUP_CHAT_ID.
    В воскресенье перед стартом (день потока 0) уходит расписание дней 1–7.
    """
    if not CHALLENGE_GROUP_CHAT_ID:
        if force:
            logger.warning("CHALLENGE_GROUP_CHAT_ID не задан — расписание не отправлено")
        return False

    try:
        group_chat_id = int(CHALLENGE_GROUP_CHAT_ID)
    except ValueError:
        logger.error("CHALLENGE_GROUP_CHAT_ID должен быть числом: %s", CHALLENGE_GROUP_CHAT_ID)
        return False

    now = _now_moscow()
    today = now.date()

    if not force:
        if is_challenge_summary_stopped():
            return False
        if not _is_schedule_time(now):
            return False
        if is_challenge_weekly_schedule_sent_on(today):
            return False

    # Участники не обязательны: расписание — анонс в группу (в т.ч. вс перед стартом, день потока 0).
    group_challenge_day = get_group_challenge_day()
    week_range = get_upcoming_week_day_range(group_challenge_day)
    if not week_range:
        logger.info("Расписание не сформировано: challenge_day=%s", group_challenge_day)
        return False

    challenge_start_id = get_group_challenge_start_id()
    if not challenge_start_id:
        logger.warning("challenge_start_id не найден — расписание не отправлено")
        return False

    from_day, to_day = week_range
    practices = _load_week_practices(challenge_start_id, from_day, to_day)
    if not practices:
        logger.warning("Нет практик для расписания дни %s–%s", from_day, to_day)
        return False

    text = build_weekly_schedule_message(from_day, to_day, practices)

    try:
        await context.bot.send_message(chat_id=group_chat_id, text=text, parse_mode="Markdown")
    except Exception as e:
        logger.error("Ошибка отправки расписания челленджа в чат %s: %s", group_chat_id, e)
        return False

    if not force:
        mark_challenge_weekly_schedule_sent(today)

    logger.info("Расписание челленджа (дни %s–%s) отправлено в чат %s", from_day, to_day, group_chat_id)
    return True
