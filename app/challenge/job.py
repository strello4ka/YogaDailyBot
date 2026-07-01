"""Отправка утренней сводки и расписания челленджа в групповой чат по расписанию."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from app.config import CHALLENGE_GROUP_CHAT_ID, DEFAULT_TZ
from app.challenge.messages import (
    CHALLENGE_DURATION,
    SCHEDULE_HOUR,
    SCHEDULE_MINUTE,
    SUMMARY_HOUR,
    SUMMARY_MINUTE,
    WEEKLY_PROGRESS_DAYS,
    build_weekly_schedule_message,
    collect_summary_data,
    detect_summary_kind,
    get_upcoming_week_day_range,
)
from data.db import (
    get_active_challenge_participants,
    get_challenge_completed_in_last_n_days,
    get_group_challenge_day,
    get_group_challenge_start_id,
    get_yoga_practice_by_challenge_order,
    get_yesterday_completed_challenge_user_ids,
    is_challenge_summary_sent_on,
    is_challenge_summary_stopped,
    is_challenge_weekly_schedule_sent_on,
    mark_challenge_summary_sent,
    mark_challenge_summary_stopped,
    mark_challenge_weekly_schedule_sent,
)

logger = logging.getLogger(__name__)
MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)


def _now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _is_summary_time(now: datetime) -> bool:
    local = now.astimezone(MOSCOW_TZ)
    return local.hour == SUMMARY_HOUR and local.minute == SUMMARY_MINUTE


def _is_schedule_time(now: datetime) -> bool:
    local = now.astimezone(MOSCOW_TZ)
    return (
        local.weekday() == 6
        and local.hour == SCHEDULE_HOUR
        and local.minute == SCHEDULE_MINUTE
    )


def _build_completed_map(participants_raw: list[tuple], kind: str) -> dict[int, int]:
    completed: dict[int, int] = {}
    for row in participants_raw:
        user_id = row[0]
        challenge_day = int(row[3])
        if kind == "final":
            n = CHALLENGE_DURATION
        elif kind == "intermediate":
            n = WEEKLY_PROGRESS_DAYS
        else:
            n = challenge_day
        completed[user_id] = get_challenge_completed_in_last_n_days(user_id, n)
    return completed


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


async def send_challenge_weekly_schedule(context: ContextTypes.DEFAULT_TYPE, *, force: bool = False) -> bool:
    """Отправляет расписание на неделю в групповой чат. force=True — без проверки времени (preview)."""
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

    participants_raw = get_active_challenge_participants()
    if not participants_raw:
        logger.info("Нет активных участников челленджа — расписание пропущено")
        return False

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
        await context.bot.send_message(chat_id=group_chat_id, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error("Ошибка отправки расписания челленджа в чат %s: %s", group_chat_id, e)
        return False

    if not force:
        mark_challenge_weekly_schedule_sent(today)

    logger.info("Расписание челленджа (дни %s–%s) отправлено в чат %s", from_day, to_day, group_chat_id)
    return True


def schedule_challenge_summary(application):
    """Регистрирует фоновые задачи сводки и расписания челленджа."""
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
        job_queue.run_repeating(
            send_challenge_weekly_schedule,
            interval=60,
            first=1,
            name="challenge_weekly_schedule",
        )
        logger.info(
            "Сводка челленджа запланирована на %02d:%02d МСК, расписание — вс %02d:%02d МСК",
            SUMMARY_HOUR,
            SUMMARY_MINUTE,
            SCHEDULE_HOUR,
            SCHEDULE_MINUTE,
        )
    except Exception as e:
        logger.error("Ошибка планирования задач челленджа: %s", e)
