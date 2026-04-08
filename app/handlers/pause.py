"""Обработчик паузы/возобновления рассылки."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from data.db import (
    get_user_notify_time,
    toggle_user_pause,
    get_users_for_pause_reminder,
    mark_pause_reminder_sent,
)

logger = logging.getLogger(__name__)
PAUSE_REMINDER_TEXTS = [
    "Пауза затянулась 🙂\nЯ на месте и жду тебя. Когда будешь готов(а), просто введи /pause и продолжим.",
    "Я соскучился по твоим практикам 🧡\nХочешь вернуться в ритм? Введи /pause.",
    "Небольшое напоминание: движение всегда можно вернуть мягко и без спешки.\nЯ бережно сохранил твой прогресс.",
]


async def pause_toggle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переключает паузу рассылки: приостановить -> продолжить -> приостановить."""
    user = update.effective_user
    message = update.message
    if not user or not message:
        return

    user_id = user.id
    notify_time = get_user_notify_time(user_id)
    if notify_time is None:
        await message.reply_text(
            "Сначала выбери время для отправки практик"
        )
        return

    success, is_paused_now, had_challenge = toggle_user_pause(user_id)
    if not success:
        await message.reply_text("Не получилось переключить режим паузы. Попробуй еще раз чуть позже.")
        return

    if is_paused_now:
        await message.reply_text(
            "Остановил ежедневную рассылку 🧡\n\n"
            "Твой прогресс полностью сохранен.\n"
            "Когда будешь готов(а) вернуться, просто снова введи /pause — и продолжим с того же места."
        )
        logger.info(f"Пользователь {user_id} поставил рассылку на паузу")
        return

    await message.reply_text(
        f"Рассылка снова активна ✔️\n\n"
        f"Продолжаем без потери прогресса — как будто паузы не было.\n"
        f"Следующая практика придет по твоему времени: {notify_time}."
    )
    logger.info(f"Пользователь {user_id} возобновил рассылку")


async def send_weekly_pause_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет пользователям в паузе напоминание не чаще 1 раза в 7 дней."""
    try:
        users = get_users_for_pause_reminder()
        if not users:
            return

        for user_id, chat_id in users:
            try:
                text = PAUSE_REMINDER_TEXTS[user_id % len(PAUSE_REMINDER_TEXTS)]
                await context.bot.send_message(chat_id=chat_id, text=text)
                mark_pause_reminder_sent(user_id)
                logger.info(f"Отправлено напоминание о паузе пользователю {user_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки напоминания о паузе пользователю {user_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка еженедельных напоминаний о паузе: {e}")


def schedule_pause_reminders(application):
    """Регистрирует фоновую задачу напоминаний для пользователей в паузе."""
    try:
        job_queue = application.job_queue
        if not job_queue:
            logger.error("JobQueue недоступен для pause-напоминаний")
            return

        job_queue.run_repeating(
            send_weekly_pause_reminders,
            interval=60 * 60 * 6,  # каждые 6 часов
            first=30,
            name="pause_weekly_reminders"
        )
        logger.info("Напоминания для пользователей в паузе запланированы")
    except Exception as e:
        logger.error(f"Ошибка планирования pause-напоминаний: {e}")
