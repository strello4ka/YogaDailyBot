"""Mode-free onboarding state machine."""

import asyncio
import html
import logging
import time
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, ReplyParameters
from telegram.ext import ApplicationHandlerStop

from app import onboarding_messages as copy
from app.keyboards import get_common_reply_keyboard, onboarding_reply_keyboard
from app.onboarding_state import load_state, pending_states, save_state
from app.rich_messages import button_row, edit_rich_message, paragraph, send_rich_message

logger = logging.getLogger(__name__)

WELCOME_BUTTONS = [["Покажи пример", "Настроить бот"]]


def _lock(context, user_id):
    return context.bot_data.setdefault("onboarding_v3_locks", {}).setdefault(user_id, asyncio.Lock())


def _new_state(update):
    user = update.effective_user
    return {
        "user_id": user.id,
        "chat_id": update.effective_chat.id,
        "name": (user.first_name or "").strip(),
        "nickname": user.username,
        "step": "welcome",
        "entered_at": time.time(),
        "reminded": [],
        "screen_id": None,
    }


async def _send_agreement(context, state):
    blocks = [
        paragraph({"type": "bold", "text": "📄 Первым шагом документы"}),
        paragraph("Чтобы пользоваться ботом, нужно принять условия пользовательского соглашения."),
        button_row([
            {"text": "Отказываюсь", "style": "link", "callback_data": f"ob3:decline:{copy.AGREEMENT_VERSION}"},
            {"text": "Принять", "style": "primary", "callback_data": f"ob3:accept:{copy.AGREEMENT_VERSION}"},
        ]),
        button_row([{"text": "Ссылка на соглашение", "url": copy.AGREEMENT_URL}]),
    ]
    return await send_rich_message(context.bot, state["chat_id"], blocks, reply_markup=ReplyKeyboardRemove())


def _agreement_result_blocks(accepted):
    status = "✅ Соглашение принято" if accepted else "Соглашение не принято"
    return [
        paragraph({"type": "bold", "text": f"📄 {status}"}),
        button_row([{"text": "Ссылка на соглашение", "url": copy.AGREEMENT_URL}]),
    ]


async def _send_step(context, state):
    step = state["step"]
    if step == "agreement":
        message = await _send_agreement(context, state)
    else:
        text, keyboard = {
            "welcome": (copy.welcome(html.escape(state.get("name") or "")), onboarding_reply_keyboard(WELCOME_BUTTONS)),
            "subscription": (copy.SUBSCRIPTION, onboarding_reply_keyboard([["Следующий шаг"]])),
            "schedule_offer": (copy.SCHEDULE_OFFER, onboarding_reply_keyboard([["Пропустить", "Настроить расписание"]])),
            "schedule_week": (copy.WEEK, onboarding_reply_keyboard([["Пропустить", "Выбрать время"]])),
            "time_input": (copy.TIME_INPUT, ReplyKeyboardRemove()),
            "confirmation": (copy.confirmation(state["time"]), onboarding_reply_keyboard([["Последний шаг"]])),
            "location": (copy.LOCATION, ReplyKeyboardRemove()),
        }[step]
        message = await context.bot.send_message(state["chat_id"], text, parse_mode="HTML", reply_markup=keyboard)
    state["screen_id"] = message.message_id
    save_state(state)


async def _transition(context, state, step, *, schedule_time=None):
    state.update(step=step, entered_at=time.time(), reminded=[])
    if step == "subscription" and not state.get("deadline_at"):
        state["deadline_at"] = time.time() + 72 * 3600
    save_state(state, schedule_time=schedule_time)
    await _send_step(context, state)


async def _finish_second_message(context, state):
    async with _lock(context, state["user_id"]):
        latest = load_state(state["user_id"])
        if not latest or latest.get("step") != "location":
            return
        message = await context.bot.send_message(
            latest["chat_id"], copy.COMPLETE, parse_mode="HTML", reply_markup=get_common_reply_keyboard()
        )
        latest.update(step="complete", screen_id=message.message_id, completed_at=time.time())
        save_state(latest, complete=True)
        await _start_pending_challenge(context, latest)


async def _finish_job(context):
    state = load_state(context.job.data["user_id"])
    if state and state.get("step") == "location":
        await _finish_second_message(context, state)


async def _finish(context, state):
    state["step"] = "location"
    state["reminded"] = []
    save_state(state)
    await _send_step(context, state)
    context.job_queue.run_once(_finish_job, timedelta(seconds=10), data={"user_id": state["user_id"]})


async def _start_pending_challenge(context, state):
    practice_id = state.pop("pending_challenge_practice_id", None)
    if practice_id is None:
        return
    save_state(state)
    from app.challenge.flow.start_flow import send_challenge_welcome_dm
    await send_challenge_welcome_dm(
        context, user_id=state["user_id"], chat_id=state["chat_id"], practice_id=practice_id,
        user_name=state.get("name"), user_nickname=state.get("nickname"),
    )


async def begin(update, context):
    """Called after the production reset has already been confirmed/applied."""
    for key in (
        "waiting_for_practice_suggestion", "waiting_for_time", "is_time_change",
        "waiting_for_challenge_time", "pending_challenge_practice_id",
        "onboarding_keyboard_chat_id", "onboarding_keyboard_message_id", "onboarding_keyboard_kind",
    ):
        context.user_data.pop(key, None)
    from app.handlers.done import cancel_done_reminders, dismiss_done_reminders
    await cancel_done_reminders(context, update.effective_user.id)
    dismiss_done_reminders(update.effective_user.id)
    state = _new_state(update)
    save_state(state)
    await _send_step(context, state)


async def start_command(update, context):
    from data.db import user_exists
    from app.keyboards import get_restart_confirm_keyboard
    from app.onboarding import START_RESTART_WARNING
    if user_exists(update.effective_user.id):
        await update.effective_message.reply_text(START_RESTART_WARNING, reply_markup=get_restart_confirm_keyboard())
        return
    from data.db import set_user_onboarding_required
    from app.onboarding import _parse_traffic_source
    set_user_onboarding_required(
        update.effective_user.id, update.effective_chat.id,
        user_name=update.effective_user.first_name, user_nickname=update.effective_user.username,
        traffic_source=_parse_traffic_source(context),
    )
    await begin(update, context)


async def restart_yes(update, context):
    query = update.callback_query
    await query.answer()
    from data.db import set_user_onboarding_required
    user = update.effective_user
    set_user_onboarding_required(user.id, update.effective_chat.id, user_name=user.first_name, user_nickname=user.username)
    try:
        await query.message.delete()
    except Exception:
        pass
    await begin(update, context)


async def agreement_callback(update, context):
    query = update.callback_query
    state = load_state(update.effective_user.id)
    parts = query.data.split(":", 2)
    action = parts[1]
    version = parts[2] if len(parts) == 3 else None
    if not state or state.get("step") != "agreement" or version != copy.AGREEMENT_VERSION:
        await query.answer("Эта версия соглашения уже не актуальна.", show_alert=True)
        return
    await query.answer()
    agreement_message_id = state.get("screen_id") or query.message.message_id
    if query.message.message_id != agreement_message_id:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
    if action == "decline":
        state["step"] = "declined"
        save_state(state)
        try:
            await edit_rich_message(context.bot, state["chat_id"], agreement_message_id, _agreement_result_blocks(False))
        except Exception:
            logger.exception("Не удалось обновить Rich Message соглашения user=%s", state["user_id"])
        await query.message.reply_text(
            "Ты не принял условия соглашения, поэтому продолжить настройку и получать практики пока нельзя.\n\n"
            "Если передумаешь, вернись к соглашению по кнопке ниже. Твои сохранённые данные останутся на месте.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Вернуться к соглашению", callback_data="ob3:return")],
                [InlineKeyboardButton("Помощь", callback_data="ob3:help")],
            ]),
        )
        return
    state["agreement_version"] = copy.AGREEMENT_VERSION
    state["agreement_accepted_at"] = time.time()
    save_state(state)
    try:
        await edit_rich_message(context.bot, state["chat_id"], agreement_message_id, _agreement_result_blocks(True))
    except Exception:
        logger.exception("Не удалось обновить Rich Message соглашения user=%s", state["user_id"])
    await _transition(context, state, "subscription")


async def agreement_aux_callback(update, context):
    query = update.callback_query
    await query.answer()
    state = load_state(update.effective_user.id)
    if not state or state.get("step") != "declined":
        return
    if query.data == "ob3:help":
        from app.handlers.help import help_command
        await help_command(update, context)
        return
    state["step"] = "agreement"
    save_state(state)
    await _send_step(context, state)


async def guard_command(update, context):
    state = load_state(update.effective_user.id) if update.effective_user else None
    text = update.effective_message.text or ""
    if state and state.get("step") != "complete" and not text.startswith("/start"):
        await update.effective_message.reply_text("Сначала закончи настройку бота 🧡")
        raise ApplicationHandlerStop


async def guard_callback(update, context):
    state = load_state(update.effective_user.id) if update.effective_user else None
    data = update.callback_query.data or ""
    if state and state.get("step") != "complete" and not data.startswith(("ob3:", "start_restart_")):
        await update.callback_query.answer("Сначала закончи настройку бота.", show_alert=True)
        raise ApplicationHandlerStop


async def handle_reply(update, context):
    """Return True when a reply belongs to an active onboarding."""
    state = load_state(update.effective_user.id)
    if not state or state.get("step") == "complete":
        return False
    if state.get("step") == "declined":
        await update.effective_message.reply_text(
            "Сначала прими пользовательское соглашение по кнопке выше."
        )
        return True
    text = update.effective_message.text
    step = state["step"]
    if step == "welcome" and text == "Покажи пример":
        from app.onboarding import _get_onboarding_example_practice, ONBOARDING_EXAMPLE_VIDEO_URL
        from app.schedule.scheduler import format_practice_message
        sample = _get_onboarding_example_practice()
        if sample:
            _, _, _, duration, channel, _, description, difficulty, *_ = sample
        else:
            duration, channel, description, difficulty = 0, "YouTube", "", None
        body = format_practice_message("Практика дня", description, duration, difficulty, channel, ONBOARDING_EXAMPLE_VIDEO_URL)
        await update.effective_message.reply_text(
            body, parse_mode="Markdown", disable_web_page_preview=False,
            reply_markup=onboarding_reply_keyboard([["Настроить бот"]]),
        )
        return True
    if step == "welcome" and text == "Настроить бот":
        await _transition(context, state, "agreement")
        return True
    if step == "subscription" and text == "Следующий шаг":
        await _transition(context, state, "schedule_offer")
        return True
    if step == "schedule_offer" and text == "Пропустить":
        await _finish(context, state)
        return True
    if step == "schedule_offer" and text == "Настроить расписание":
        await _transition(context, state, "schedule_week")
        return True
    if step == "schedule_week" and text == "Пропустить":
        await _finish(context, state)
        return True
    if step == "schedule_week" and text == "Выбрать время":
        await _transition(context, state, "time_input")
        return True
    if step == "time_input":
        from app.daily.set_time import validate_time_format
        valid, value = validate_time_format(text)
        if not valid:
            await update.effective_message.reply_text(f"🚨 {value}\n\nПопробуй еще раз в формате ЧЧ.ММ")
            return True
        state["time"] = value
        await _transition(context, state, "confirmation", schedule_time=value)
        return True
    if step == "confirmation" and text == "Последний шаг":
        await _finish(context, state)
        return True
    return True


async def reminders_job(context):
    now = time.time()
    for state in pending_states():
        if state.get("step") == "location":
            await _finish_second_message(context, state)
            continue
        if state.get("step") in ("complete", "declined"):
            continue
        if state.get("deadline_at") and now >= state["deadline_at"] and state.get("agreement_version") == copy.AGREEMENT_VERSION:
            await _finish(context, state)
            continue
        if state.get("step") in ("schedule_week", "time_input", "confirmation"):
            continue
        due = [i for i, hours in enumerate((1, 24)) if now >= state["entered_at"] + hours * 3600 and i not in state.get("reminded", [])]
        if not due:
            continue
        index = max(due)
        reminder_markup = None
        if state.get("step") == "agreement":
            reminder_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Принять", callback_data=f"ob3:accept:{copy.AGREEMENT_VERSION}")]])
        await context.bot.send_message(
            state["chat_id"], copy.GENERAL_REMINDERS[index],
            reply_markup=reminder_markup,
            reply_parameters=ReplyParameters(message_id=state.get("screen_id"), allow_sending_without_reply=True),
        )
        state["reminded"] = sorted(set(state.get("reminded", []) + due))
        save_state(state)


def schedule_onboarding_reminders(application):
    application.job_queue.run_repeating(reminders_job, interval=60, first=10, name="onboarding_v3_reminders")
