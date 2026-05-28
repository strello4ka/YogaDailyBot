"""Еженедельные напоминания пользователям в режиме By mood,
которые давно не запрашивали практику. Логика повторяет pause-напоминания."""

import logging

from telegram.ext import ContextTypes

from data.db import (
    get_users_for_by_mood_reminder,
    mark_by_mood_reminder_sent,
)

logger = logging.getLogger(__name__)

# Тексты — пока такие же, как для паузы; можно заменить позже.
BY_MOOD_REMINDER_TEXTS = [
    "Пауза затянулась 💔",
    "Скучаю по твоим практикам 🧘‍♂️",
    "Я не пишу «вернись», я пишу «как ты там»",
    "Я изменился: стал мягче, стабильнее и с хорошим расписанием ✨",
    "Это не расставание, это «нам нужно время»",
    "Я не навязываюсь...🪫",
    "Я все еще думаю о тебе 📆",

]


async def send_weekly_by_mood_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Шлёт напоминание не чаще раза в 7 дней пользователям By mood без активности 7+ дней."""
    try:
        users = get_users_for_by_mood_reminder()
        if not users:
            return

        for user_id, chat_id, reminder_step in users:
            try:
                text = BY_MOOD_REMINDER_TEXTS[
                    reminder_step % len(BY_MOOD_REMINDER_TEXTS)
                ]
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown",
                )
                mark_by_mood_reminder_sent(user_id)
                logger.info(f"Отправлено By mood-напоминание пользователю {user_id}")
            except Exception as e:
                logger.error(
                    f"Ошибка отправки By mood-напоминания пользователю {user_id}: {e}"
                )
    except Exception as e:
        logger.error(f"Ошибка еженедельных By mood-напоминаний: {e}")


def schedule_by_mood_reminders(application):
    """Регистрирует фоновую задачу: каждые 6 часов проверяет неактивных By mood-пользователей."""
    try:
        job_queue = application.job_queue
        if not job_queue:
            logger.error("JobQueue недоступен для By mood-напоминаний")
            return

        job_queue.run_repeating(
            send_weekly_by_mood_reminders,
            interval=60 * 60 * 6,
            first=45,
            name="by_mood_weekly_reminders",
        )
        logger.info("Напоминания для неактивных By mood-пользователей запланированы")
    except Exception as e:
        logger.error(f"Ошибка планирования By mood-напоминаний: {e}")
