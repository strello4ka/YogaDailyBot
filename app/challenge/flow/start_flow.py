"""Основной сценарий старта челленджа в личке: приветствие и выбор времени."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from app.challenge.cohort import get_challenge_start_date, is_cohort_configured
from app.config import DEFAULT_TZ
from app.keyboards import get_common_reply_keyboard, get_welcome_keyboard
from app.onboarding_messages import WEEK_DESCRIPTION, expandable_quote, quote
from data.db import (
    complete_user_challenge_setup,
    get_current_weekday,
    start_user_challenge_setup,
)

logger = logging.getLogger(__name__)

PENDING_CHALLENGE_PRACTICE_KEY = "pending_challenge_practice_id"
CHALLENGE_TIME_FLOW_KEY = "waiting_for_challenge_time"
MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)

CHALLENGE_TIME_INPUT_TEXT = (
    "*Введи время в формате ЧЧ.ММ (например, 09.30)*\n\n"
    "PS. Время учитывается по МСК"
)


def build_challenge_welcome_text() -> str:
    """Приветствие с датой старта потока в формате ДД.ММ."""
    start = get_challenge_start_date()
    start_label = start.strftime("%d.%m") if start else "[дата старта]"
    end_label = (start + timedelta(days=27)).strftime("%d.%m") if start else "[дата окончания]"
    return (
        "<b>Ура, ты в потоке</b> 🧡\n\n"
        "Давай <b>выберем время</b>, в которое ты хочешь получать ежедневные практики, "
        f"с <b>{start_label}</b> по <b>{end_label}</b>\n\n{expandable_quote(WEEK_DESCRIPTION)}"
    )


async def send_challenge_welcome_dm(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    chat_id: int,
    practice_id: int,
    user_name: Optional[str] = None,
    user_nickname: Optional[str] = None,
) -> tuple[bool, str]:
    """Записывает setup в БД и шлёт приветствие + выбор времени в личку."""
    from data.db import is_user_onboarding_required

    if is_user_onboarding_required(user_id):
        from app.onboarding_state import load_state, save_state
        state = load_state(user_id)
        if not state or state.get("step") in ("declined", "complete"):
            return False, "сначала нужно завершить /start"
        state["pending_challenge_practice_id"] = practice_id
        save_state(state)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Сначала закончи знакомство с ботом. После онбординга я продолжу настройку челленджа 🧡",
        )
        return True, "ожидает завершения онбординга"

    if not start_user_challenge_setup(
        user_id,
        chat_id,
        practice_id,
        user_name=user_name,
        user_nickname=user_nickname,
    ):
        return False, "нет в базе (нужен /start)"

    # Практика из предыдущего режима больше не должна порождать напоминание
    # после перехода в челлендж, в том числе через failsafe после рестарта.
    from app.handlers.done import cancel_done_reminders, dismiss_done_reminders

    await cancel_done_reminders(context, user_id)
    dismiss_done_reminders(user_id)

    try:
        time_choice_message = await context.bot.send_message(
            chat_id=chat_id,
            text=build_challenge_welcome_text(),
            reply_markup=get_welcome_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Не удалось отправить welcome челленджа user=%s: %s", user_id, e)
        return False, f"ошибка отправки: {e}"

    # Новые напоминания для первичного ввода времени челленджа не добавляем.
    return True, ""


async def begin_challenge_time_selection_flow(
    update: Update, context: ContextTypes.DEFAULT_TYPE, practice_id: int
) -> None:
    """Единый вход в челлендж: приветствие + inline «Выбрать время»."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    ok, err = await send_challenge_welcome_dm(
        context,
        user_id=user.id,
        chat_id=chat_id,
        practice_id=practice_id,
        user_name=user.first_name,
        user_nickname=user.username,
    )
    if not ok:
        await update.message.reply_text(
            "Сначала нажми /start, а потом запусти челлендж ещё раз."
            if "нет в базе" in err
            else f"Не получилось запустить челлендж: {err}"
        )
        return
    context.user_data[PENDING_CHALLENGE_PRACTICE_KEY] = practice_id


async def handle_challenge_time_choice_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Кнопка «Выбрать время» внутри сценария челленджа."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    from app.onboarding import remove_callback_keyboard, strip_inline_keyboard

    await remove_callback_keyboard(query)
    chat_id = update.effective_chat.id
    strip_message_id = context.user_data.pop("daily_time_choice_message_id", None)
    context.user_data.pop("daily_time_choice_chat_id", None)
    await strip_inline_keyboard(context, chat_id, strip_message_id)
    context.user_data.pop("waiting_for_practice_suggestion", None)
    context.user_data.pop("is_time_change", None)
    context.user_data["waiting_for_time"] = True
    context.user_data[CHALLENGE_TIME_FLOW_KEY] = True

    user_id = update.effective_user.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=CHALLENGE_TIME_INPUT_TEXT,
        parse_mode="Markdown",
    )
    # Для первичного выбора времени челленджа отдельные напоминания не отправляются.


def _validate_time_format(time_str: str) -> tuple[bool, str]:
    time_str = time_str.strip().replace(".", ":")
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if not match:
        return False, "Хм, такой формат времени я не понимаю."
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour < 0 or hour > 23:
        return False, "Ой, часы должны быть от 0 до 23."
    if minute < 0 or minute > 59:
        return False, "Ой, минуты должны быть от 00 до 59."
    return True, f"{hour:02d}:{minute:02d}"


def _should_send_challenge_practice_immediately(notify_time: str) -> bool:
    """True, если поток уже идёт и выбранное время на сегодня уже наступило (МСК)."""
    if not is_cohort_configured():
        return False
    start = get_challenge_start_date()
    now = datetime.now(MOSCOW_TZ)
    if start is None or now.date() < start:
        return False
    return notify_time <= now.strftime("%H:%M")


async def handle_challenge_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ввод времени для челленджа: сохраняем время и активируем bot_mode='challenge'."""
    is_valid, result = _validate_time_format(update.message.text)
    if not is_valid:
        await update.message.reply_text(
            f"🚨 {result}\n\n"
            "Попробуй еще раз в формате ЧЧ.ММ"
        )
        return

    selected_time = result
    user = update.effective_user
    chat_id = update.effective_chat.id

    from app.onboarding import cancel_reminders

    await cancel_reminders(context, user.id)
    if not complete_user_challenge_setup(
        user.id,
        chat_id,
        selected_time,
        user_name=user.first_name,
        user_nickname=user.username,
    ):
        context.user_data["waiting_for_time"] = True
        context.user_data[CHALLENGE_TIME_FLOW_KEY] = True
        await update.message.reply_text(
            "Не получилось сохранить время и запустить челлендж.\n\n"
            "Пришли время ещё раз в формате ЧЧ.ММ (например, 09.30)."
        )
        return

    context.user_data.pop("waiting_for_time", None)
    context.user_data.pop(CHALLENGE_TIME_FLOW_KEY, None)
    context.user_data.pop(PENDING_CHALLENGE_PRACTICE_KEY, None)

    send_now = _should_send_challenge_practice_immediately(selected_time)
    await update.message.reply_text(
        (
            "Готово ✅\n\n"
            f"Твое время <b>{selected_time}</b>.\n"
            "Длительность челленджа: <b>28 дней</b>\n\n"
            "До встречи на коврике 🧡\n\n"
            + quote("Дисциплина - это не контроль над собой. Это форма любви к своему будущему.")
        ),
        reply_markup=get_common_reply_keyboard(),
        parse_mode="HTML",
    )
    from app.keyboards import COMMON_REPLY_KEYBOARD_VERSION
    from data.db import mark_reply_keyboard_version
    mark_reply_keyboard_version(user.id, COMMON_REPLY_KEYBOARD_VERSION)

    if send_now:
        try:
            from app.schedule.scheduler import send_practice_to_user

            await send_practice_to_user(
                context, user.id, chat_id, get_current_weekday()
            )
        except Exception as e:
            logger.warning(
                "Не удалось сразу отправить практику челленджа user=%s: %s",
                user.id,
                e,
            )
