"""Основной сценарий старта челленджа в личке: приветствие и выбор времени."""

from __future__ import annotations

import logging
import re
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from app.keyboards import get_main_reply_keyboard, get_welcome_keyboard
from data.db import complete_user_challenge_setup, start_user_challenge_setup

logger = logging.getLogger(__name__)

PENDING_CHALLENGE_PRACTICE_KEY = "pending_challenge_practice_id"
CHALLENGE_TIME_FLOW_KEY = "waiting_for_challenge_time"

CHALLENGE_WELCOME_TEXT = (
    "*Ура, ты в челлендже* 🧡\n\n"
    "Давай *выберем время*, в которое ты хочешь получать ежедневные практики, начиная с завтрашнего дня"
)

CHALLENGE_TIME_INPUT_TEXT = (
    "*Введи время в формате ЧЧ.ММ (например, 09.30)*\n\n"
    "PS. Время учитывается по МСК"
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
    if not start_user_challenge_setup(
        user_id,
        chat_id,
        practice_id,
        user_name=user_name,
        user_nickname=user_nickname,
    ):
        return False, "нет в базе (нужен /start)"

    try:
        time_choice_message = await context.bot.send_message(
            chat_id=chat_id,
            text=CHALLENGE_WELCOME_TEXT,
            reply_markup=get_welcome_keyboard(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Не удалось отправить welcome челленджа user=%s: %s", user_id, e)
        return False, f"ошибка отправки: {e}"

    from app.onboarding import schedule_time_pick_reminders

    if hasattr(context, "job_queue") and context.job_queue is not None:
        await schedule_time_pick_reminders(
            context, chat_id, user_id, time_choice_message.message_id
        )
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

    from app.onboarding import remove_callback_keyboard, schedule_reminders, strip_inline_keyboard

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
    if hasattr(context, "job_queue") and context.job_queue is not None:
        await schedule_reminders(context, chat_id, user_id)


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
    await update.message.reply_text(
        (
            "Готово ✔️\n\n"
            f"Твоё время *{selected_time}*.\n"
            "Длительность челленджа — *28 дней*.\n"
            f"В понедельник придёт твоя первая практика!\n\n"
            "Уже жду начала 🧡"
        ),
        parse_mode="Markdown",
    )
    await update.message.reply_text(
        (
            "Внизу у тебя появились кнопки:\n\n"
            "🕓 *Изменить время* — жми, чтобы изменить время рассылки\n"
            "💡 *Советы* — жми обязательно\n"
            "🪫 *Пауза* — приостановить или возобновить ежедневную рассылку\n"
            "✨ *Еще практики* — дополнительные практики по настроению (как в режиме By mood, но без отключения ежедневной рассылки)\n\n"
            "Также есть *Меню*, где можно посмотреть свой прогресс, избранные практики, задонатить и найти другую полезную инфу"
        ),
        reply_markup=get_main_reply_keyboard(),
        parse_mode="Markdown",
    )
