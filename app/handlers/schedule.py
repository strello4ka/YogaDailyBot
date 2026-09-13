"""Schedule menu entry and first-time schedule setup."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.onboarding_messages import WEEK_DESCRIPTION, expandable_quote
from app.daily.set_time import validate_time_format
from data.db import (
    get_user_schedule_settings,
    get_yoga_practice_by_challenge_order,
    save_user_time,
    toggle_user_pause,
)

logger = logging.getLogger(__name__)


SCHEDULE_MENU_TIME_KEY = "waiting_for_schedule_menu_time"

FIRST_SETUP_TEXT = (
    "Давай настроим удобное время для практик 🧡\n\n"
    "<b>В какое время хочешь получать ежедневные видео, начиная с завтрашнего дня?</b>\n\n"
    + expandable_quote(WEEK_DESCRIPTION)
)

TIME_INPUT_TEXT = (
    "<b>Введи время в формате ЧЧ.ММ</b>\n"
    "(например, 09.30)\n\n"
    "PS. Время учитывается по МСК"
)


def _is_never_configured(settings) -> bool:
    return not settings or settings.get("notify_time") in (None, "", "00:00")


def _management_keyboard(*, challenge: bool, paused: bool) -> InlineKeyboardMarkup:
    toggle_label = "Возобновить рассылку" if paused else "Остановить рассылку"
    rows = [
        [InlineKeyboardButton(toggle_label, callback_data="schedule_toggle")],
        [InlineKeyboardButton("Изменить время", callback_data="schedule_change_time")],
    ]
    if challenge:
        rows.append([InlineKeyboardButton("Расписание челленджа", callback_data="schedule_challenge_week")])
    return InlineKeyboardMarkup(rows)


def _management_text(settings) -> tuple[str, bool]:
    is_challenge = settings.get("bot_mode") == "challenge" and settings.get("challenge_start_id") is not None
    if is_challenge:
        return f"Сейчас ты в челлендже 🧡\nТвоё время — {settings['notify_time']}", True
    status = "приостановлена 🪫" if settings.get("paused") else "активна ✅"
    return f"Рассылка {status}\nТвое время сейчас — {settings['notify_time']}", False


def cancel_schedule_menu_time(context):
    """Cancel only this menu's time prompt, leaving other flows untouched."""
    if not context.user_data.pop(SCHEDULE_MENU_TIME_KEY, None):
        return False
    context.user_data.pop("waiting_for_time", None)
    context.user_data.pop("is_time_change", None)
    return True


async def cancel_schedule_menu_time_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commands take precedence over an unfinished schedule-menu prompt."""
    cancel_schedule_menu_time(context)


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = get_user_schedule_settings(update.effective_user.id)
    if not _is_never_configured(settings):
        text, is_challenge = _management_text(settings)
        await update.effective_message.reply_text(
            text,
            reply_markup=_management_keyboard(
                challenge=is_challenge,
                paused=bool(settings.get("paused")),
            ),
        )
        return

    cancel_schedule_menu_time(context)
    await update.effective_message.reply_text(
        FIRST_SETUP_TEXT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Выбрать время", callback_data="schedule_pick_time")]]
        ),
    )


async def schedule_pick_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    context.user_data[SCHEDULE_MENU_TIME_KEY] = True
    context.user_data["waiting_for_time"] = True
    context.user_data.pop("is_time_change", None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=TIME_INPUT_TEXT,
        parse_mode="HTML",
    )


async def schedule_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    before = get_user_schedule_settings(user_id)
    is_challenge = bool(
        before
        and before.get("bot_mode") == "challenge"
        and before.get("challenge_start_id") is not None
    )
    if is_challenge:
        await query.message.reply_text(
            "Когда челлендж закончится, рассылка остановится.\n"
            "Если хочешь завершить челлендж досрочно, введи /challenge_off"
        )
        return

    success, is_paused_now, _had_challenge = toggle_user_pause(user_id)
    if not success:
        await query.message.reply_text("Не получилось переключить рассылку. Попробуй еще раз чуть позже.")
        return

    if is_paused_now:
        text = (
            "<b>Остановил ежедневную рассылку 🪫</b>\n"
            "Твой прогресс полностью сохранен и ждет тебя!\n"
            "Когда захочешь вернуться, просто жми кнопку <b>Возобновить рассылку</b> — "
            "продолжим с того же места"
        )
    else:
        notify_time = (before or {}).get("notify_time") or "—"
        text = (
            "<b>Ураа, я знал, что ты вернешься! Рассылка снова активна 🔋</b>\n"
            "Продолжаем без потери прогресса, как будто паузы и не было.\n"
            f"Следующая практика придет по твоему времени: <b>{notify_time}</b>"
        )

    after = get_user_schedule_settings(user_id)
    if after:
        management_text, is_challenge = _management_text(after)
        try:
            await query.edit_message_text(
                text=management_text,
                reply_markup=_management_keyboard(
                    challenge=is_challenge,
                    paused=bool(after.get("paused")),
                ),
            )
        except Exception:
            logger.exception("Не удалось обновить экран расписания user=%s", user_id)
    await query.message.reply_text(text, parse_mode="HTML")


async def schedule_change_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.callback_query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    from app.daily.set_time import handle_set_time_callback
    await handle_set_time_callback(update, context)


async def schedule_challenge_week_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    settings = get_user_schedule_settings(update.effective_user.id)
    if not settings or settings.get("bot_mode") != "challenge" or not settings.get("challenge_start_id"):
        await query.message.reply_text("Ты уже не участвуешь в активном челлендже.")
        return

    from app.challenge.cohort import get_upcoming_week_day_range
    from app.challenge.week_schedule.messages import build_weekly_schedule_message

    week_range = get_upcoming_week_day_range(settings.get("challenge_day", 0))
    if not week_range:
        await query.message.reply_text("Челлендж уже завершён — расписания на следующую неделю нет.")
        return
    from_day, to_day = week_range
    practices = []
    for day in range(from_day, to_day + 1):
        row = get_yoga_practice_by_challenge_order(settings["challenge_start_id"], day)
        if row:
            practices.append((day, row[1], row[4], int(row[3] or 0)))
    await query.message.reply_text(
        build_weekly_schedule_message(from_day, to_day, practices),
        parse_mode="Markdown",
    )


async def handle_schedule_menu_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get(SCHEDULE_MENU_TIME_KEY):
        return False

    is_valid, result = validate_time_format(update.effective_message.text or "")
    if not is_valid:
        await update.effective_message.reply_text(
            f"🚨 {result}\n\nПопробуй еще раз в формате ЧЧ.ММ"
        )
        return True

    user = update.effective_user
    saved = save_user_time(
        user.id,
        update.effective_chat.id,
        result,
        user.first_name,
        user_nickname=user.username,
        reset_days=False,
    )
    if not saved:
        await update.effective_message.reply_text(
            "Не получилось сохранить время. Попробуй ввести его ещё раз чуть позже."
        )
        return True

    cancel_schedule_menu_time(context)
    await update.effective_message.reply_text(
        "Готово ✅\n\n"
        f"Завтра в <b>{result}</b> начнется наш YogaDaily путь!\n\n"
        "Изменить время и остановить рассылку можно в любой момент",
        parse_mode="HTML",
    )
    return True
