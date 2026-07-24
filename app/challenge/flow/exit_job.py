"""Автозавершение челленджа в личку на день 29."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from app.config import CHALLENGE_GROUP_CHAT_ID, DEFAULT_TZ
from app.challenge.cohort import CHALLENGE_DURATION, FINAL_SUMMARY_DAY, SUMMARY_HOUR, SUMMARY_MINUTE
from app.challenge.flow.exit_flow import finish_challenge_for_user
from data.db import (
    get_active_challenge_participants,
    get_challenge_completed_in_last_n_days,
    get_challenge_users_for_auto_exit,
    get_group_challenge_day,
    is_challenge_auto_exit_sent_on,
    is_challenge_summary_sent_on,
    is_challenge_summary_stopped,
    mark_challenge_auto_exit_sent,
)

logger = logging.getLogger(__name__)
MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)


def _now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _is_summary_time(now: datetime) -> bool:
    local = now.astimezone(MOSCOW_TZ)
    return local.hour == SUMMARY_HOUR and local.minute == SUMMARY_MINUTE


async def send_challenge_auto_exit(context: ContextTypes.DEFAULT_TYPE, *, force: bool = False) -> bool:
    """Личное автозавершение всем с bot_mode=challenge (день 29).

    Не вызывается из preview. Если задана группа — ждём финальную сводку за сегодня.
    """
    now = _now_moscow()
    today = now.date()
    group_day = get_group_challenge_day()

    if group_day != FINAL_SUMMARY_DAY:
        return False
    if not force:
        if is_challenge_auto_exit_sent_on(today):
            return False
        if not _is_summary_time(now):
            return False
        if CHALLENGE_GROUP_CHAT_ID:
            if not is_challenge_summary_sent_on(today) and not is_challenge_summary_stopped():
                if get_active_challenge_participants():
                    return False

    users = get_challenge_users_for_auto_exit()
    if not users:
        logger.info("Нет участников для автозавершения челленджа")
        if not force:
            mark_challenge_auto_exit_sent(today)
        return True

    ok_count = 0
    for user_id, chat_id, _name, _nick in users:
        if not chat_id:
            logger.warning("Автозавершение: нет chat_id у user=%s", user_id)
            continue
        completed = get_challenge_completed_in_last_n_days(int(user_id), CHALLENGE_DURATION)
        if await finish_challenge_for_user(
            context,
            user_id=int(user_id),
            chat_id=int(chat_id),
            completed=completed,
        ):
            ok_count += 1

    if not force:
        mark_challenge_auto_exit_sent(today)

    logger.info("Автозавершение челленджа: отправлено %s из %s", ok_count, len(users))
    return ok_count > 0 or not users
