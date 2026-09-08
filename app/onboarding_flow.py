"""Новый онбординг; старый onboarding.py пока обслуживает совместимость Challenge."""

import asyncio
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters
from telegram.helpers import escape_markdown

from app import onboarding_messages as texts
from app.onboarding_state import load_state, save_state, pending_states
from app.rich_messages import paragraph, button_row, send_rich_message, edit_rich_message
from app.keyboards import get_common_reply_keyboard

logger = logging.getLogger(__name__)

BUTTONS = {
    "welcome": [("Настроить бот", "agreement")],
    "agreement": [("Принять", "accept")],
    "subscription": [("Следующий шаг", "offer")],
    "offer": [("Настроить расписание", "week")],
    "week": [("Выбрать время", "time")],
    "time": [("Выбрать время", "time")],
    "confirmation": [("Последний шаг", "finish")],
}


def user_lock(context, user_id):
    locks = context.bot_data.setdefault("onboarding_locks", {})
    return locks.setdefault(user_id, asyncio.Lock())


def keyboard(step, *, reminder=False):
    buttons = list(BUTTONS.get(step, []))
    if step == "welcome" and not reminder:
        buttons.insert(0, ("Посмотреть пример", "example"))
    if step == "offer" and not reminder:
        buttons.insert(0, ("Пропустить", "finish"))
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"ob2:{step}:{action}")]
        for label, action in buttons
    ])


def agreement_blocks(*, active=True):
    blocks = [
        paragraph({"type": "bold", "text": "Первым шагом документы"}),
        paragraph("📄 Пользовательское соглашение.\nЧтобы пользоваться ботом, нужно принять условия соглашения."),
        paragraph("Тестовая версия: ссылка на соглашение пока является заглушкой."),
    ]
    if active:
        blocks.append(button_row([
            {"text": "Отказываюсь", "style": "link", "callback_data": "ob2:agreement:decline"},
            {"text": "Принять", "style": "primary", "callback_data": "ob2:agreement:accept"},
        ]))
    blocks.append(button_row([{"text": "Ссылка на соглашение", "url": texts.AGREEMENT_URL}]))
    return blocks


async def strip_buttons(context, state):
    for message_id in state.get("message_ids", []):
        try:
            if state["step"] == "agreement" and message_id == state.get("screen_id"):
                await edit_rich_message(context.bot, state["chat_id"], message_id, agreement_blocks(active=False))
            else:
                await context.bot.edit_message_reply_markup(
                    chat_id=state["chat_id"], message_id=message_id, reply_markup=None)
        except Exception:
            logger.info("Не удалось снять устаревшие кнопки онбординга user=%s", state["user_id"])


async def show_step(context, state):
    step = state["step"]
    if step == "agreement":
        message = await send_rich_message(context.bot, state["chat_id"], agreement_blocks())
    else:
        text = {
            "welcome": texts.welcome_text(escape_markdown(state.get("name") or "друг", version=1)),
            "subscription": texts.SUBSCRIPTION_TEXT,
            "offer": texts.SCHEDULE_OFFER_TEXT,
            "week": texts.WEEK_TEXT,
            "time": texts.TIME_TEXT,
            "confirmation": texts.confirmation_text(state.get("time", "")),
            "complete": ("" if state.get("automatic") else "Онбординг пройден!\n\n") + texts.FINAL_BODY,
        }[step]
        markup = get_common_reply_keyboard() if step == "complete" else keyboard(step)
        if step == "time":
            markup = None
        message = await context.bot.send_message(
            chat_id=state["chat_id"], text=text, parse_mode="Markdown", reply_markup=markup)
    state["screen_id"] = message.message_id
    state.setdefault("message_ids", []).append(message.message_id)
    state["display_pending"] = False
    save_state(state)


async def transition(context, state, step, *, schedule_time=None):
    await strip_buttons(context, state)
    state.update(step=step, entered_at=time.time(), reminded=[], message_ids=[], display_pending=True)
    if step == "subscription":
        state.setdefault("deadline_at", time.time() + 72 * 3600)
    save_state(state, schedule_time=schedule_time, complete=step == "complete")
    await show_step(context, state)
    if step == "complete" and state.get("pending_challenge_practice_id"):
        from app.challenge.flow.start_flow import send_challenge_welcome_dm

        practice_id = state.pop("pending_challenge_practice_id")
        save_state(state)
        ok, error = await send_challenge_welcome_dm(
            context,
            user_id=state["user_id"],
            chat_id=state["chat_id"],
            practice_id=practice_id,
            user_name=state.get("name"),
            user_nickname=state.get("nickname"),
        )
        if not ok:
            logger.error(
                "Не удалось продолжить Challenge после онбординга user=%s: %s",
                state["user_id"], error,
            )


async def start_command(update, context):
    if not update.effective_user or not update.effective_message or update.effective_chat.type != "private":
        return
    user = update.effective_user
    async with user_lock(context, user.id):
        state = load_state(user.id)
        if state is None:
            from data.db import user_exists, is_user_onboarding_required
            if user_exists(user.id) and not is_user_onboarding_required(user.id):
                await update.effective_message.reply_text(
                    "Выбирай практику по кнопкам или открой «Расписание» в меню 🧡",
                    reply_markup=get_common_reply_keyboard())
                return
            from app.onboarding import _parse_traffic_source
            state = dict(user_id=user.id, chat_id=update.effective_chat.id, name=user.first_name,
                         nickname=user.username, traffic_source=_parse_traffic_source(context),
                         step="welcome", entered_at=time.time(), reminded=[], message_ids=[])
            save_state(state, create_user=True)
        elif state["step"] == "declined":
            await transition(context, state, "agreement")
            return
        elif state["step"] == "challenge":
            await update.effective_message.reply_text("Продолжай настройку челленджа в его сообщении.")
            return
        await show_step(context, state)


async def callback(update, context):
    query = update.callback_query
    await query.answer()
    async with user_lock(context, update.effective_user.id):
        state = load_state(update.effective_user.id)
        _, expected, action = query.data.split(":", 2)
        if not state or state["step"] != expected:
            return
        if action == "example" and expected == "welcome":
            from app.onboarding import ONBOARDING_EXAMPLE_VIDEO_URL
            await strip_buttons(context, state)
            message = await context.bot.send_message(
                chat_id=state["chat_id"], text=ONBOARDING_EXAMPLE_VIDEO_URL,
                reply_markup=keyboard("welcome", reminder=True), disable_web_page_preview=False)
            state["message_ids"] = [message.message_id]
            save_state(state)
            return
        if action == "decline" and expected == "agreement":
            await strip_buttons(context, state)
            state["step"] = "declined"
            save_state(state)
            await query.message.reply_text("Без принятия соглашения настройка недоступна. Вернуться можно через /start.")
            return
        if action == "accept" and expected == "agreement":
            state["agreement_version"] = texts.AGREEMENT_VERSION
            state["agreement_accepted_at"] = time.time()
            state["agreement_message_id"] = state.get("screen_id")
            await transition(context, state, "subscription")
            return
        if action == "finish" and expected in ("offer", "confirmation"):
            if state.get("agreement_version") == texts.AGREEMENT_VERSION:
                await transition(context, state, "complete")
            return
        target = {("welcome", "agreement"): "agreement", ("subscription", "offer"): "offer",
                  ("offer", "week"): "week", ("week", "time"): "time"}.get((expected, action))
        if target:
            await transition(context, state, target)
        elif expected == "time" and action == "time":
            await show_step(context, state)


async def handle_time_input(update, context):
    """True, если текст принадлежит новому онбордингу, включая восстановление после рестарта."""
    async with user_lock(context, update.effective_user.id):
        state = load_state(update.effective_user.id)
        if not state or state["step"] in ("complete", "declined", "challenge"):
            return False
        if state["step"] != "time":
            return True
        from app.daily.set_time import validate_time_format
        valid, value = validate_time_format(update.effective_message.text)
        if not valid:
            await update.effective_message.reply_text(f"🚨 {value}\n\nПопробуй еще раз в формате ЧЧ.ММ")
            return True
        state["time"] = value
        await transition(context, state, "confirmation", schedule_time=value)
        return True


async def legacy_callback(update, context):
    """Старые кнопки не переключают режим и не сбрасывают данные."""
    await update.callback_query.answer()
    await start_command(update, context)


async def reminders_job(context):
    for candidate in pending_states():
        async with user_lock(context, candidate["user_id"]):
            try:
                state = load_state(candidate["user_id"])
                if not state or state["step"] not in BUTTONS:
                    continue
                from data.db import get_user_bot_mode
                if get_user_bot_mode(state["user_id"]) == "challenge":
                    # Не завершать онбординг поверх отдельно начатого челленджа.
                    continue
                if state.get("display_pending"):
                    await show_step(context, state)
                    continue
                now = time.time()
                if (state.get("deadline_at", float("inf")) < now
                        and state.get("agreement_version") == texts.AGREEMENT_VERSION):
                    state["automatic"] = True
                    await transition(context, state, "complete")
                    continue
                due = [i for i, hours in enumerate((1, 24))
                       if now >= state["entered_at"] + hours * 3600 and i not in state["reminded"]]
                if not due:
                    continue
                # После длительного простоя не посылать сразу оба напоминания.
                index = max(due)
                message = await context.bot.send_message(
                    chat_id=state["chat_id"], text=texts.REMINDERS[index],
                    reply_markup=keyboard(state["step"], reminder=True),
                    reply_parameters=ReplyParameters(message_id=state["screen_id"], allow_sending_without_reply=True))
                state["reminded"] = sorted(set(state["reminded"] + due))
                state["message_ids"].append(message.message_id)
                save_state(state)
            except Exception:
                logger.exception("Ошибка напоминания нового онбординга user=%s", candidate["user_id"])


def schedule_onboarding_reminders(application):
    application.job_queue.run_repeating(reminders_job, interval=60, first=10, name="onboarding_v2_reminders")
