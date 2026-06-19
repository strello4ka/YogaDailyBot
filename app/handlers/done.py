"""Обработчик «✅ Я сделал!» и напоминания, если практика не отмечена."""

import logging
import random
from datetime import datetime, timedelta, time
from typing import Optional
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from app.config import DEFAULT_TZ
from app.handlers.progress import format_progress_stats, format_similar_result_line
from data.db import (
    get_completed_count,
    get_similar_result_percent,
    get_streak_days,
    is_pending_practice_log,
    is_user_eligible_for_done_reminder,
    mark_practice_completed_today,
)

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)

# Не слать напоминания после этого времени (МСК)
REMINDER_CUTOFF_TIME = time(22, 0)
EVENING_REMINDER_TIME = time(19, 30)

# Тексты разделены по типу напоминания: «+1 ч» — фокус на кнопке, «19:30» — мягче, про саму практику.
DONE_REMINDER_TEXTS_ONE_HOUR = [
    "Кнопка «✅ Я сделал!» ждет нажатий",
    "Прогресс сам себя не увеличит - как выполнишь практику, жми кнопку «✅ Я сделал!»",
    "«✅ Я сделал!» — самая недооценённая кнопка в чате",
]

DONE_REMINDER_TEXTS_EVENING = [
    "Практика все еще ждет тебя 🧡",
    "Кажется ты кое-что забыл...Самое время расстилать коврик!",
    "Похоже, практика осталась невыполненной, но все еще можно исправить",
]

ACHIEVEMENT_MESSAGES = {
    1: "Ура! Начало положено, заглядывай еще 🫂",
    2: "Ого, ты набираешь обороты 🌀",
    5: "Давай дневник, ставлю 5️⃣",
    10: "Первая ДЕСЯТОЧКА! Ты настоящий йога-двигатель 🔋",
    15: "Легенда коврика, официально ✨",
    20: "20 ПРАКТИК!!!",
    25: "Ритм держишь как профи 🧡 ",
    30: "30 — Такой темп пугает и восхищает одновременно 🌀",
    40: "40 ПРАКТИК 💪💪💪",
    50: "ПОЛСОТНИ — уровень МАШИНА 🦾",
    60: "Ты уже сверхчеловек на коврике...",
    70: "Кажется, тебя уже не остановить 🧘‍♂️",
    80: "До сотни рукой подать — добивай красиво 🪄",
    90: "90! До сотни один вдох и выдох ✨",
    100: "100!!! Всё, теперь ты легально гуру йоги 🧘‍♂️🧘‍♂️🧘‍♂️",
    150: "Ты не тренируешься — ты доминируешь 🔋",
    200: "200!!!! Спокойно… ты вообще человек?",
    250: "Ты пример того, как работает система и характер 💙",
    300: "300!!! Ты просто монстр 💪",
    365: "365 дней в году и столько раз ты занимался йогой вместе мной, наши отношения переходят на новый уровень 🫂",
}

STREAK_ACHIEVEMENT_MESSAGES = {
    3: "Три дня подряд — чувствую серьезные намерения 🔋",
    5: "Пять дней без перерыва! Кажется, тебя уже не остановить 🧘‍♂️",
    7: "Неделя без пропусков, круто держишь ритм 🧡",
    10: "Ииииии это страйк!",
    14: "Две недели подряд! Очень горжусь твоей дисциплиной 🫂",
    21: "Три недели - это уже уровень мастера привычек 🧘‍♂️",
    28: "Четыре недели без остановки..МАШИНА",
    30: "Месяц без единого пропуска!!! Ты уже сверхчеловек на коврике 🌀",
    40: "40 ДНЕЙ С ПРАКТИКОЙ! Ты не тренируешься — ты доминируешь...",
    50: "ПОЛСОТНИ — теперь ты легально гуру йоги 🧘‍♂️🧘‍♂️🧘‍♂️",
    60: "Два месяца день за днем…ты вообще человек?",

}


def _achievement_title(n: int, streak: int) -> str:
    """Заголовок после «Я сделал!»: веха по серии важнее вехи по числу практик."""
    if streak in STREAK_ACHIEVEMENT_MESSAGES:
        return STREAK_ACHIEVEMENT_MESSAGES[streak]
    return ACHIEVEMENT_MESSAGES.get(n, "Ты супер🧡")


def pick_done_reminder_text(reminder_kind: str) -> str:
    """Случайная фраза из пула под конкретный тип напоминания."""
    if reminder_kind == "evening":
        return random.choice(DONE_REMINDER_TEXTS_EVENING)
    return random.choice(DONE_REMINDER_TEXTS_ONE_HOUR)


def _now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _is_before_cutoff(when: datetime) -> bool:
    local = when.astimezone(MOSCOW_TZ)
    return (local.hour, local.minute) < (REMINDER_CUTOFF_TIME.hour, REMINDER_CUTOFF_TIME.minute)


def _delay_for_one_hour_reminder(now: datetime) -> Optional[timedelta]:
    """+1 ч от отправки, только в тот же календарный день и строго до 22:00 МСК."""
    if not _is_before_cutoff(now):
        return None
    fire_at = now + timedelta(hours=1)
    if fire_at.date() != now.date() or not _is_before_cutoff(fire_at):
        return None
    return timedelta(hours=1)


def _first_reminder_at(now: datetime) -> Optional[datetime]:
    """Момент первого напоминания (+1 ч) или None, если оно в этот день не планируется."""
    if _delay_for_one_hour_reminder(now) is None:
        return None
    return now + timedelta(hours=1)


def _delay_for_evening_reminder(now: datetime) -> Optional[timedelta]:
    """Второе напоминание в 19:30 — только если первое (+1 ч) уже успеет до 19:30."""
    if not _is_before_cutoff(now):
        return None
    evening = datetime.combine(now.date(), EVENING_REMINDER_TIME, tzinfo=MOSCOW_TZ)
    if now >= evening:
        return None
    first_at = _first_reminder_at(now)
    if first_at is None or first_at >= evening:
        return None
    return evening - now


def _job_names(user_id: int) -> list[str]:
    return [f"done_reminder_1h_{user_id}", f"done_reminder_1930_{user_id}"]


async def cancel_done_reminders(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    if not getattr(context, "job_queue", None):
        return
    job_queue = context.job_queue
    for job_name in _job_names(user_id):
        try:
            for job in job_queue.get_jobs_by_name(job_name):
                job.schedule_removal()
        except Exception as e:
            logger.debug("cancel_done_reminders %s: %s", job_name, e)
        try:
            scheduler = job_queue.scheduler
            job = scheduler.get_job(job_name)
            if job:
                scheduler.remove_job(job_name)
        except Exception:
            pass


async def _send_done_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    data = job.data or {}
    user_id = data.get("user_id")
    chat_id = data.get("chat_id")
    log_id = data.get("log_id")
    sent_date = data.get("sent_date")
    sent_at_iso = data.get("sent_at")
    reminder_kind = data.get("reminder_kind", "1h")

    if not all((user_id, chat_id, log_id, sent_date)):
        return

    now = _now_moscow()
    if reminder_kind == "evening" and sent_at_iso:
        try:
            sent_at = datetime.fromisoformat(sent_at_iso)
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=MOSCOW_TZ)
            else:
                sent_at = sent_at.astimezone(MOSCOW_TZ)
        except ValueError:
            return
        if now < sent_at + timedelta(hours=1):
            return

    if now.date().isoformat() != sent_date:
        return
    if not _is_before_cutoff(now):
        return
    if not is_user_eligible_for_done_reminder(user_id):
        return
    if not is_pending_practice_log(user_id, log_id):
        return

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=pick_done_reminder_text(reminder_kind),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Ошибка напоминания о практике user=%s log=%s: %s", user_id, log_id, e)


async def schedule_done_reminders(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    log_id: int,
) -> None:
    """Напоминания: +1 ч (первое), 19:30 (второе — только если первое успевает до 19:30)."""
    if not log_id or not getattr(context, "job_queue", None):
        if not getattr(context, "job_queue", None):
            logger.warning("JobQueue недоступен — напоминания «Я сделал» не запланированы")
        return

    await cancel_done_reminders(context, user_id)

    now = _now_moscow()
    sent_date = now.date().isoformat()
    job_data = {
        "chat_id": chat_id,
        "user_id": user_id,
        "log_id": log_id,
        "sent_date": sent_date,
        "sent_at": now.isoformat(),
    }

    delay_1h = _delay_for_one_hour_reminder(now)
    if delay_1h is not None:
        context.job_queue.run_once(
            _send_done_reminder_job,
            when=delay_1h,
            data={**job_data, "reminder_kind": "1h"},
            name=f"done_reminder_1h_{user_id}",
        )

    delay_evening = _delay_for_evening_reminder(now)
    if delay_evening is not None:
        context.job_queue.run_once(
            _send_done_reminder_job,
            when=delay_evening,
            data={**job_data, "reminder_kind": "evening"},
            name=f"done_reminder_1930_{user_id}",
        )


def _done_text(n: int, streak: int, similar_line: str) -> str:
    title = _achievement_title(n, streak)
    return f"{title}\n\n{format_progress_stats(n, streak)}{similar_line}"


async def handle_practice_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """«✅ Я сделал!»: отметка последней практики и отмена напоминаний."""
    query = update.callback_query
    if not query:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await query.answer("Ошибка: пользователь не определён.")
        return

    ok = mark_practice_completed_today(user_id)
    await cancel_done_reminders(context, user_id)
    await query.answer()
    if ok:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        n = get_completed_count(user_id)
        streak = get_streak_days(user_id)
        similar_percent = get_similar_result_percent(user_id, bucket_size=5, min_completed=3)
        similar_line = format_similar_result_line(n, similar_percent)
        text = _done_text(n, streak, similar_line)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode="Markdown",
        )
