"""Завершение челленджа с переходом в общий интерфейс без выбора режима."""

from __future__ import annotations

import logging
from typing import Optional

from telegram.ext import ContextTypes

from app.challenge.cohort import CHALLENGE_DURATION
from app.keyboards import get_common_reply_keyboard
from data.db import clear_user_challenge

logger = logging.getLogger(__name__)


def build_challenge_finished_text(completed: Optional[int] = None) -> str:
    """Текст завершения челленджа; completed — личный N из 28 (опционально)."""
    result_line = ""
    if completed is not None:
        result_line = f"Твой результат: *{completed}/{CHALLENGE_DURATION}* дней\n"
    return (
        "*Челлендж завершен* ✔️\n\n"
        f"{result_line}"
        "Какими бы ни были цифры, я так рад, что ты участвовал 🧡\n\n"
        "Продолжай пользоваться мной, чтобы сохранить привычку.\n"
        "Ты можешь как выбирать практики по кнопкам так и настроить расписание, "
        "чтобы получать их регулярно, прямо как в челлендже!\n\n"
        "В меню доступны твоё избранное, прогресс, управление подпиской, помощь и советы ↙️"
    )


async def finish_challenge_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    user_id: int,
    chat_id: int,
    completed: Optional[int] = None,
) -> bool:
    """Выход из челленджа: clear + сообщение с общей клавиатурой."""
    from app.daily.extra_practices import strip_extra_practices_inline_keyboards
    from app.handlers.done import cancel_done_reminders, dismiss_done_reminders

    if not clear_user_challenge(user_id):
        logger.error(
            "Не удалось сохранить завершение челленджа user=%s; финальное сообщение не отправлено",
            user_id,
        )
        return False
    await cancel_done_reminders(context, user_id)
    dismiss_done_reminders(user_id)
    await strip_extra_practices_inline_keyboards(context.bot, user_id)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=build_challenge_finished_text(completed),
            reply_markup=get_common_reply_keyboard(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("Не удалось отправить завершение челленджа user=%s: %s", user_id, e)
        return False

    return True
