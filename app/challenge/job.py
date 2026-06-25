"""Отправка утренней сводки челленджа в групповой чат по расписанию."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from app.config import CHALLENGE_GROUP_CHAT_ID, DEFAULT_TZ
from app.challenge.messages import (
    CHALLENGE_DURATION,
    SUMMARY_HOUR,
    SUMMARY_MINUTE,
    collect_summary_data,
    detect_summary_kind,
)
from data.db import (
    get_active_challenge_participants,
    get_challenge_completed_in_last_n_days,
    get_group_challenge_day,
    get_yesterday_completed_challenge_user_ids,
    is_challenge_summary_sent_on,
    is_challenge_summary_stopped,
    mark_challenge_summary_sent,
    mark_challenge_summary_stopped,
)

logger = logging.getLogger(__name__)
MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)


def _now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _is_summary_time(now: datetime) -> bool:
    local = now.astimezone(MOSCOW_TZ)
    return local.hour == SUMMARY_HOUR and local.minute == SUMMARY_MINUTE


def _build_completed_map(participants_raw: list[tuple], kind: str) -> dict[int, int]:
    completed: dict[int, int] = {}
    for row in participants_raw:
        user_id = row[0]
        challenge_day = int(row[3])
        n = CHALLENGE_DURATION if kind == "final" else challenge_day
        completed[user_id] = get_challenge_completed_in_last_n_days(user_id, n)
    return completed


async def send_challenge_group_summary(context: ContextTypes.DEFAULT_TYPE, *, force: bool = False) -> bool:
    """Отправляет утреннюю сводку в групповой чат. force=True — без проверки времени (preview)."""
    if not CHALLENGE_GROUP_CHAT_ID:
        if force:
            logger.warning("CHALLENGE_GROUP_CHAT_ID не задан — сводка не отправлена")
        return False

    try:
        group_chat_id = int(CHALLENGE_GROUP_CHAT_ID)
    except ValueError:
        logger.error("CHALLENGE_GROUP_CHAT_ID должен быть числом: %s", CHALLENGE_GROUP_CHAT_ID)
        return False

    now = _now_moscow()
    today = now.date()
    stopped = is_challenge_summary_stopped()

    if not force:
        if stopped:
            return False
        if not _is_summary_time(now):
            return False
        if is_challenge_summary_sent_on(today):
            return False

    participants_raw = get_active_challenge_participants()
    if not participants_raw:
        logger.info("Нет активных участников челленджа — сводка пропущена")
        return False

    group_challenge_day = get_group_challenge_day()
    kind = detect_summary_kind(group_challenge_day, stopped=False if force else stopped)
    if kind is None:
        logger.info(
            "Сводка не сформирована: challenge_day=%s stopped=%s force=%s",
            group_challenge_day,
            stopped,
            force,
        )
        return False

    yesterday = today - timedelta(days=1)
    yesterday_done_ids = get_yesterday_completed_challenge_user_ids(yesterday)
    completed_map = _build_completed_map(participants_raw, kind)

    _, text = collect_summary_data(
        participants_raw,
        yesterday_done_ids,
        group_challenge_day,
        stopped=False,
        completed_by_user_id=completed_map,
    )
    if not text:
        return False

    try:
        await context.bot.send_message(chat_id=group_chat_id, text=text)
    except Exception as e:
        logger.error("Ошибка отправки сводки челленджа в чат %s: %s", group_chat_id, e)
        return False

    if not force:
        mark_challenge_summary_sent(today)
        if kind == "final":
            mark_challenge_summary_stopped()

    logger.info("Сводка челленджа (%s) отправлена в чат %s", kind, group_chat_id)
    return True


def schedule_challenge_summary(application):
    """Регистрирует фоновую задачу утренней сводки челленджа."""
    try:
        job_queue = application.job_queue
        if not job_queue:
            logger.error("JobQueue недоступен для сводки челленджа")
            return

        job_queue.run_repeating(
            send_challenge_group_summary,
            interval=60,
            first=1,
            name="challenge_group_summary",
        )
        logger.info("Утренняя сводка челленджа запланирована на %02d:%02d МСК", SUMMARY_HOUR, SUMMARY_MINUTE)
    except Exception as e:
        logger.error("Ошибка планирования сводки челленджа: %s", e)
