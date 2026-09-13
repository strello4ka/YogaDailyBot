"""Post-challenge schedule offer and its persisted reminders."""

import json
import logging
import time
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.onboarding_messages import quote
from app.challenge.cohort import CHALLENGE_DURATION
from data.db import save_user_time_after_challenge
from data.postgres_db import _delete_system_state, _get_system_state, _set_system_state

logger = logging.getLogger(__name__)
PREFIX = "post_challenge_offer:"
REMINDERS = (
    "Хочешь сохранить ритм после челленджа?",
    "Продолжить получать практики ежедневно или пока остановиться — решать тебе.",
)


def finished_text(completed: Optional[int] = None) -> str:
    """Первое сообщение при завершении челленджа."""
    result_line = ""
    if completed is not None:
        result_line = f"Твой результат: *{completed}/{CHALLENGE_DURATION}* дней\n"
    return (
        "*Челлендж завершен* ✅\n\n"
        f"{result_line}"
        "Какими бы ни были цифры, мы классно провели время 🧡"
    )


def _key(user_id):
    return f"{PREFIX}{user_id}"


def load(user_id):
    raw = _get_system_state(_key(user_id))
    return json.loads(raw) if raw else None


def save(state):
    return _set_system_state(_key(state["user_id"]), json.dumps(state, ensure_ascii=False))


def cancel(user_id):
    return _delete_system_state(_key(user_id))


def keyboard(value):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Не хочу", callback_data="pc:no"), InlineKeyboardButton("Изменить время", callback_data="pc:change")],
        [InlineKeyboardButton(f"Продолжить в {value}", callback_data="pc:continue")],
    ])


def offer_text(value):
    """Второе сообщение через 10 секунд: предложение продолжить расписание."""
    return (
        f"🕐 <b>Хочешь продолжить получать практики каждый день в {value}, как во время челленджа?</b>\n\n"
        "Это поможет закрепить привычку и продолжить заниматься регулярно.\n\n"
        + quote("Твои ежедневные привычки - твое лучшее лекарство. Или худшее.")
    )


async def send_offer(context, state):
    message = await context.bot.send_message(
        state["chat_id"], offer_text(state["time"]), parse_mode="HTML", reply_markup=keyboard(state["time"])
    )
    state.update(message_id=message.message_id, entered_at=time.time(), reminded=[], stage="offer")
    save(state)


async def delayed_offer_job(context):
    state = load(context.job.data["user_id"])
    if state and state.get("stage") == "waiting":
        await send_offer(context, state)


async def callback(update, context):
    query = update.callback_query
    await query.answer()
    state = load(update.effective_user.id)
    if not state:
        return
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    if query.data == "pc:no":
        cancel(state["user_id"])
        await query.message.reply_text(
            "Понял! Полный чилл после челленджа...\n\n"
            "Настроить расписание можно в любой момент в меню.\n\nДо встречи 🧡"
        )
        return
    if query.data == "pc:continue":
        await _save_schedule(
            update,
            state,
            state["time"],
            success_text=(
                "Юхууу..нас не остановить!\n\n"
                "Изменить время и остановить рассылку можно в меню → «Расписание»."
            ),
        )
        return
    if state.get("stage") != "time_input":
        state.update(stage="time_input", entered_at=time.time(), reminded=[])
    save(state)
    await query.message.reply_text(
        "<b>Введи время в формате ЧЧ.ММ (например, 09.30)</b>\n\nPS. Время учитывается по МСК",
        parse_mode="HTML",
    )


async def _save_schedule(update, state, value, *, success_text=None):
    user = update.effective_user
    if not save_user_time_after_challenge(user.id, update.effective_chat.id, value, user.first_name, user.username):
        await update.effective_message.reply_text("Не получилось сохранить время. Попробуй ещё раз.")
        return True
    cancel(user.id)
    if success_text is None:
        success_text = (
            "Готово ✅\n\n"
            f"Завтра в <b>{value}</b> начнется наш YogaDaily путь!\n\n"
            "Изменить время и остановить рассылку можно в меню → «🕐 Расписание»."
        )
    await update.effective_message.reply_text(success_text, parse_mode="HTML")
    return True


async def handle_time_input(update, context):
    state = load(update.effective_user.id)
    if not state or state.get("stage") != "time_input":
        return False
    from app.daily.set_time import validate_time_format
    valid, value = validate_time_format(update.effective_message.text)
    if not valid:
        state["reminders_disabled"] = True
        save(state)  # Ввод остаётся активным, прекращаются только напоминания.
        await update.effective_message.reply_text(f"🚨 {value}\n\nПопробуй еще раз в формате ЧЧ.ММ")
        return True
    return await _save_schedule(update, state, value)


async def cancel_on_other_activity(update, context):
    user = update.effective_user
    if not user or not load(user.id):
        return
    if update.callback_query and (update.callback_query.data or "").startswith("pc:"):
        return
    state = load(user.id)
    if state and state.get("stage") == "time_input" and update.effective_message:
        text = update.effective_message.text or ""
        permanent_buttons = {
            "ленивые дни", "без коврика", "здоровая спина", "расслабление", "мини",
            "strello4ka", "хард", "практика дня", "САМ решу", "расписание",
        }
        if not text.startswith("/") and text not in permanent_buttons:
            return
    cancel(user.id)


async def reminders_job(context):
    from data.db import get_user_bot_mode
    from data.postgres_db import get_connection
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM system_state WHERE key LIKE %s", (f"{PREFIX}%",))
            states = [json.loads(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()
    now = time.time()
    for state in states:
        if state.get("stage") == "waiting" and now >= state.get("entered_at", now) + 10:
            await send_offer(context, state)
            continue
        if get_user_bot_mode(state["user_id"]) == "daily":
            cancel(state["user_id"])
            continue
        if state.get("stage") not in ("offer", "time_input") or state.get("reminders_disabled"):
            continue
        due = [i for i, hours in enumerate((1, 24)) if now >= state["entered_at"] + hours * 3600 and i not in state.get("reminded", [])]
        if not due:
            continue
        index = max(due)
        await context.bot.send_message(
            state["chat_id"], REMINDERS[index], reply_markup=keyboard(state["time"])
        )
        state["reminded"] = sorted(set(state.get("reminded", []) + due))
        save(state)


def schedule_reminders(application):
    application.job_queue.run_repeating(reminders_job, interval=60, first=10, name="post_challenge_reminders")
