"""Обработчик «✅ Я сделал!» и напоминания, если практика не отмечена."""

import logging
import random
from datetime import datetime, timedelta, time
from typing import Optional
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from app.config import DEFAULT_TZ
from app.block import mark_blocked_if_forbidden
from app.handlers.favorites import (
    message_is_favorites_carousel,
    strip_done_from_favorites_carousel,
)
from app.handlers.progress import (
    format_challenge_progress_line,
    format_progress_stats,
    format_social_proof_line,
)
from app.practice_markup import keep_favorite_button_on_message
from app.practice_ref import parse_practice_callback
from data.db import (
    clear_last_favorites_carousel_message,
    get_completed_count,
    get_users_for_done_evening_reminder,
    get_streak_days,
    has_completed_practice_today,
    has_uncompleted_practice_sent_today,
    is_user_eligible_for_done_reminder,
    list_completed_today_practice_messages,
    list_stale_done_button_messages,
    list_stale_favorites_carousel_messages,
    mark_practice_completed_by_practice_id,
    mark_practice_completed_today,
)

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)

EVENING_REMINDER_TIME = time(19, 30)

DONE_REMINDER_TEXTS_EVENING = [
    "Практика все еще ждет тебя 🧡",
    "Кажется ты кое-что забыл...Самое время расстилать коврик!",
    "Кнопка «✅ Я сделал!» ждет нажатий",
    "Прогресс сам себя не увеличит - как выполнишь практику, жми ✅",
    "«✅ Я сделал!» — самая недооценённая кнопка в чате",
    "Похоже, практика осталась невыполненной, но все еще можно исправить",
]

ACHIEVEMENT_MESSAGES = {
    1: "Ура! Начало положено, заглядывай еще 🫂",
    2: "Ого, ты набираешь обороты 🌀",
    5: "Давай дневник, ставлю 5️⃣",
    10: "Первая ДЕСЯТОЧКА! Ты настоящий йога-двигатель 🔋",
    15: "{name} — легенда коврика, официально ✨",
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


def _display_name(user) -> str:
    """Имя для ачивки: имя в Telegram → @ник → пусто (тогда «Ты супер»)."""
    if not user:
        return ""
    first_name = (user.first_name or "").strip()
    if first_name:
        return first_name
    username = (user.username or "").strip()
    if username:
        return f"@{username}"
    return ""


def _format_achievement_text(template: str, name: str) -> str:
    """Подставляет {name} в шаблон ачивки, если плейсхолдер есть."""
    if "{name}" in template:
        # Если имени/ника нет — не подставляем пустоту в спец-ачивки
        return template.format(name=name or "Ты")
    return template


def _achievement_title(n: int, streak: int, name: str) -> str:
    """Заголовок после «Я сделал!»: веха по серии важнее вехи по числу практик."""
    if streak in STREAK_ACHIEVEMENT_MESSAGES:
        return _format_achievement_text(STREAK_ACHIEVEMENT_MESSAGES[streak], name)
    template = ACHIEVEMENT_MESSAGES.get(n)
    if template is None:
        # Стандартный текст: «Катя, ты супер» / «@nick, ты супер» / «Ты супер»
        if name:
            return f"{name}, ты супер🧡"
        return "Ты супер🧡"
    return _format_achievement_text(template, name)


def pick_done_reminder_text() -> str:
    """Случайная фраза для вечернего напоминания (19:30)."""
    return random.choice(DONE_REMINDER_TEXTS_EVENING)


def _now_moscow() -> datetime:
    return datetime.now(MOSCOW_TZ)


def _delay_for_evening_reminder(now: datetime) -> Optional[timedelta]:
    """Напоминание в 19:30 МСК в день отправки практики (если практика пришла до 19:30)."""
    evening = datetime.combine(now.date(), EVENING_REMINDER_TIME, tzinfo=MOSCOW_TZ)
    if now >= evening:
        return None
    return evening - now


def _job_names(user_id: int) -> list[str]:
    return [f"done_reminder_1h_{user_id}", f"done_reminder_1930_{user_id}"]


def dismiss_done_reminders(user_id: int) -> None:
    """Помечает неотмеченные практики как без вечернего напоминания (/start, /change_mode)."""
    from data.db import dismiss_done_reminders as dismiss_in_db

    dismiss_in_db(user_id)


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


async def _strip_done_button_targets(bot, targets) -> int:
    """Снимает «Я сделал!» с переданных сообщений. Возвращает число успешных снятий."""
    stripped = 0
    for user_id, chat_id, message_id, practice_id, practice_catalog in targets:
        try:
            await keep_favorite_button_on_message(
                bot,
                chat_id,
                message_id,
                user_id,
                practice_id=practice_id,
                practice_catalog=practice_catalog,
            )
            stripped += 1
        except Exception as e:
            logger.debug(
                "strip_done_buttons user=%s msg=%s: %s",
                user_id,
                message_id,
                e,
            )
    return stripped


async def _strip_stale_favorites_carousels(bot, user_id: Optional[int] = None) -> int:
    """Снимает «Я сделал!» с каруселей /favorite не за сегодня."""
    targets = list_stale_favorites_carousel_messages()
    if user_id is not None:
        targets = [t for t in targets if t[0] == user_id]
    stripped = 0
    for uid, chat_id, message_id, practice_id, practice_catalog in targets:
        try:
            await strip_done_from_favorites_carousel(
                bot, chat_id, message_id, uid, practice_id, practice_catalog
            )
            clear_last_favorites_carousel_message(uid)
            stripped += 1
        except Exception as e:
            logger.debug(
                "strip_favorites_done user=%s msg=%s: %s",
                uid,
                message_id,
                e,
            )
    return stripped


async def strip_previous_day_done_button(
    bot,
    chat_id: int,
    user_id: int,
) -> None:
    """Снимает «Я сделал!» со ВСЕХ неотмеченных практик пользователя не за сегодня.

    Вызывается при каждой новой отправке: в списке только сообщения не за сегодня,
    сегодняшние кнопки не трогаем. Нужно как fallback, если полночь не отработала
    (например, локальный тест), и чтобы дочистить хвосты после прошлых багов.
    """
    targets = [t for t in list_stale_done_button_messages() if t[0] == user_id]
    stripped = 0
    if targets:
        stripped = await _strip_done_button_targets(bot, targets)
    fav_stripped = await _strip_stale_favorites_carousels(bot, user_id=user_id)
    total = stripped + fav_stripped
    if total:
        logger.info(
            "Снято кнопок «Я сделал!» (fallback при отправке) user=%s: %s",
            user_id,
            total,
        )


async def _send_done_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """19:30 МСК — одно напоминание, если сегодня ещё ни одна практика не отмечена."""
    job = context.job
    data = job.data or {}
    user_id = data.get("user_id")
    chat_id = data.get("chat_id")
    sent_date = data.get("sent_date")
    if not all((user_id, chat_id, sent_date)):
        return

    now = _now_moscow()
    if now.date().isoformat() != sent_date:
        return
    if not is_user_eligible_for_done_reminder(user_id):
        return
    if has_completed_practice_today(user_id):
        return
    if not has_uncompleted_practice_sent_today(user_id):
        return

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=pick_done_reminder_text(),
            parse_mode="Markdown",
        )
        # После успешной отправки больше не напоминаем за текущий день.
        dismiss_done_reminders(user_id)
    except Exception as e:
        if not mark_blocked_if_forbidden(user_id, e):
            logger.error("Ошибка напоминания о практике user=%s: %s", user_id, e)


async def schedule_done_reminders(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    log_id: int,
) -> None:
    """Планирует одно напоминание в 19:30 МСК (если практика пришла до 19:30)."""
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
    }

    delay_evening = _delay_for_evening_reminder(now)
    if delay_evening is not None:
        context.job_queue.run_once(
            _send_done_reminder_job,
            when=delay_evening,
            data=job_data,
            name=f"done_reminder_1930_{user_id}",
        )


async def send_evening_done_reminders_failsafe_job(
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Резервная отправка после 19:30 МСК, чтобы переживать перезапуски бота."""
    now = _now_moscow()
    evening = datetime.combine(now.date(), EVENING_REMINDER_TIME, tzinfo=MOSCOW_TZ)
    if now < evening:
        return

    users = get_users_for_done_evening_reminder(EVENING_REMINDER_TIME.strftime("%H:%M:%S"))
    if not users:
        return

    for user_id, chat_id in users:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=pick_done_reminder_text(),
                parse_mode="Markdown",
            )
            dismiss_done_reminders(user_id)
            logger.info("Отправлено резервное 19:30-напоминание user=%s", user_id)
        except Exception as e:
            if not mark_blocked_if_forbidden(user_id, e):
                logger.error(
                    "Ошибка резервного 19:30-напоминания user=%s: %s",
                    user_id,
                    e,
                )


def schedule_done_evening_reminders(application) -> None:
    """Фоновая проверка каждые 5 минут: догоняет пропущенные 19:30-напоминания."""
    try:
        job_queue = application.job_queue
        if not job_queue:
            logger.error("JobQueue недоступен для резервных 19:30-напоминаний")
            return
        job_queue.run_repeating(
            send_evening_done_reminders_failsafe_job,
            interval=60 * 5,
            first=20,
            name="done_evening_reminders_failsafe",
        )
        logger.info("Резервные 19:30-напоминания «Я сделал!» запланированы")
    except Exception as e:
        logger.error("Ошибка планирования резервных 19:30-напоминаний: %s", e)


async def strip_stale_done_buttons_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """В 00:00 МСК снимает «Я сделал!» со всех неотмеченных практик не за сегодня."""
    targets = list_stale_done_button_messages()
    stripped = await _strip_done_button_targets(context.bot, targets) if targets else 0
    fav_stripped = await _strip_stale_favorites_carousels(context.bot)
    logger.info(
        "Снято кнопок «Я сделал!» после полуночи: практики %s из %s, избранное %s",
        stripped,
        len(targets),
        fav_stripped,
    )


def schedule_strip_done_buttons_midnight(application) -> None:
    """Снятие «Я сделал!» каждый день в 00:00 МСК (прод всегда онлайн)."""
    try:
        job_queue = application.job_queue
        if not job_queue:
            logger.error("JobQueue недоступен — снятие кнопок «Я сделал!» не запланировано")
            return
        job_queue.run_daily(
            strip_stale_done_buttons_job,
            time=time(0, 0, tzinfo=MOSCOW_TZ),
            name="strip_done_buttons_midnight",
        )
        logger.info("Снятие кнопок «Я сделал!» запланировано на 00:00 МСК")
    except Exception as e:
        logger.error("Ошибка планирования снятия кнопок «Я сделал!»: %s", e)


def _done_text(n: int, streak: int, similar_line: str, name: str, user_id: int) -> str:
    title = _achievement_title(n, streak, name)
    challenge_line = format_challenge_progress_line(user_id)
    return f"{title}\n\n{format_progress_stats(n, streak, challenge_line)}{similar_line}"


async def _strip_done_on_completed_messages(
    bot,
    user_id: int,
    fallback_chat_id: Optional[int] = None,
    fallback_message_id: Optional[int] = None,
    fallback_practice_id: Optional[int] = None,
    fallback_reply_markup=None,
) -> None:
    """Снимает «Я сделал!» со всех отмеченных сегодня сообщений (+ нажатое сообщение)."""
    seen = set()
    targets = list_completed_today_practice_messages(user_id)
    if fallback_chat_id and fallback_message_id:
        targets = list(targets) + [
            (fallback_chat_id, fallback_message_id, fallback_practice_id, None)
        ]

    for chat_id, message_id, practice_id, practice_catalog in targets:
        key = (chat_id, message_id)
        if key in seen:
            continue
        seen.add(key)
        await keep_favorite_button_on_message(
            bot,
            chat_id,
            message_id,
            user_id,
            reply_markup=fallback_reply_markup if message_id == fallback_message_id else None,
            practice_id=practice_id,
            practice_catalog=practice_catalog,
        )


async def handle_practice_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """«✅ Я сделал!»: отметка практики и отмена напоминаний."""
    query = update.callback_query
    if not query:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await query.answer("Ошибка: пользователь не определён.")
        return

    data = query.data or ""
    practice_id = None
    practice_catalog = None
    if data.startswith("practice_done:"):
        practice_id, practice_catalog = parse_practice_callback(data, "practice_done")
        if practice_id is None:
            await query.answer("Ошибка.")
            return

    is_carousel = message_is_favorites_carousel(
        query.message.reply_markup if query.message else None
    )

    if practice_id is not None:
        ok = mark_practice_completed_by_practice_id(
            user_id,
            practice_id,
            practice_catalog or "yoga",
            only_sent_today=not is_carousel,
            allow_create_log=is_carousel,
            telegram_message_id=(
                query.message.message_id if query.message and not is_carousel else None
            ),
        )
    else:
        ok = mark_practice_completed_today(user_id)

    await query.answer()

    if ok:
        await cancel_done_reminders(context, user_id)
        if not is_carousel and query.message:
            await _strip_done_on_completed_messages(
                context.bot,
                user_id,
                fallback_chat_id=query.message.chat_id,
                fallback_message_id=query.message.message_id,
                fallback_practice_id=practice_id,
                fallback_reply_markup=query.message.reply_markup,
            )
        elif is_carousel and query.message and practice_id is not None:
            await strip_done_from_favorites_carousel(
                context.bot,
                query.message.chat_id,
                query.message.message_id,
                user_id,
                practice_id,
                practice_catalog or "yoga",
            )
            await _strip_done_on_completed_messages(context.bot, user_id)

        n = get_completed_count(user_id)
        streak = get_streak_days(user_id)
        similar_line = format_social_proof_line(user_id)
        name = _display_name(update.effective_user)
        text = _done_text(n, streak, similar_line, name, user_id)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode="Markdown",
        )
    elif is_carousel and query.message and practice_id is not None:
        # Уже отмечено / вчерашняя кнопка в избранном — убираем «Я сделал!», навигация остаётся
        await strip_done_from_favorites_carousel(
            context.bot,
            query.message.chat_id,
            query.message.message_id,
            user_id,
            practice_id,
            practice_catalog or "yoga",
        )
    elif not is_carousel and query.message:
        # Вчерашняя кнопка или уже отмечено — убираем «Я сделал!»
        await keep_favorite_button_on_message(
            context.bot,
            query.message.chat_id,
            query.message.message_id,
            user_id,
            reply_markup=query.message.reply_markup,
            practice_id=practice_id,
            practice_catalog=practice_catalog,
        )
