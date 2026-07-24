"""Регистрация фоновых задач челленджа (сводка, расписание, автовыход)."""

import logging

from app.challenge.cohort import (
    FINAL_SUMMARY_DAY,
    SCHEDULE_HOUR,
    SCHEDULE_MINUTE,
    SUMMARY_HOUR,
    SUMMARY_MINUTE,
)
from app.challenge.flow.exit_job import send_challenge_auto_exit
from app.challenge.week_schedule.job import send_challenge_weekly_schedule
from app.challenge.summary.job import send_challenge_group_summary

logger = logging.getLogger(__name__)


def schedule_challenge_jobs(application):
    """Регистрирует фоновые задачи сводки, расписания и автозавершения."""
    try:
        job_queue = application.job_queue
        if not job_queue:
            logger.error("JobQueue недоступен для задач челленджа")
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
        job_queue.run_repeating(
            send_challenge_auto_exit,
            interval=60,
            first=1,
            name="challenge_auto_exit",
        )
        logger.info(
            "Сводка челленджа запланирована на %02d:%02d МСК, расписание — вс %02d:%02d МСК, автозавершение — день %s",
            SUMMARY_HOUR,
            SUMMARY_MINUTE,
            SCHEDULE_HOUR,
            SCHEDULE_MINUTE,
            FINAL_SUMMARY_DAY,
        )
    except Exception as e:
        logger.error("Ошибка планирования задач челленджа: %s", e)
