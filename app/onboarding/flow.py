"""Mode-free onboarding state machine."""

import asyncio
import html
import logging
import time
from datetime import datetime, timedelta

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, ReplyKeyboardRemove, ReplyParameters)
from telegram.ext import ApplicationHandlerStop

from app.onboarding import messages as copy
from app.config import SUBSCRIPTION_ONBOARDING_ENABLED
from app.keyboards import COMMON_REPLY_KEYBOARD_VERSION, get_common_reply_keyboard, onboarding_reply_keyboard
from app.onboarding.state import load_state, pending_states, save_state
from app.rich_messages import button_row, edit_rich_message, paragraph, send_rich_message

logger = logging.getLogger(__name__)

WELCOME_BUTTONS = [["Покажи пример", "Настроить бот"]]


def _subscription_step_enabled(context, user_id):
    from app.subscription.access import repository_for
    return SUBSCRIPTION_ONBOARDING_ENABLED or repository_for(context, user_id) is not None


async def _subscription_variant(context, user_id):
    """Use durable access history, not a restarted onboarding state."""
    from app.subscription.access import AccessState, repository_for
    repository = repository_for(context, user_id)
    if repository is None:
        return "new"
    subscription = await asyncio.to_thread(repository.get, user_id)
    if subscription is None:
        return "new"
    if subscription.state(datetime.now().astimezone()) != AccessState.FREE:
        return "active"
    return "used" if subscription.trial is not None else "new"


def _used_subscription_keyboard(context):
    return onboarding_reply_keyboard([["Продолжить бесплатно"]])


async def _send_onboarding_tariffs(context, chat_id):
    url = context.bot_data.get('subscription_miniapp_url', '')
    if url:
        from app.subscription.subscription_menu import tariff_keyboard
        from app.subscription.messages import TARIFF_PROMPT
        await context.bot.send_message(chat_id, TARIFF_PROMPT, reply_markup=tariff_keyboard(url))


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
        if step == "welcome":
            text = copy.welcome(html.escape(state.get("name") or ""))
            keyboard = onboarding_reply_keyboard(WELCOME_BUTTONS)
        elif step == "subscription":
            if await _subscription_variant(context, state["user_id"]) == "used":
                text = copy.SUBSCRIPTION_USED
                if not context.bot_data.get("subscription_miniapp_url"):
                    text = text.replace("\n\nСмотри тарифы ниже 👇", "")
                keyboard = _used_subscription_keyboard(context)
            else:
                text, keyboard = copy.SUBSCRIPTION, onboarding_reply_keyboard([["Начать 14 дней бесплатно"]])
        elif step == "schedule_offer":
            text = copy.SCHEDULE_OFFER
            keyboard = onboarding_reply_keyboard([["Пропустить", "Настроить расписание"]])
        elif step == "time_input":
            text, keyboard = copy.TIME_INPUT, ReplyKeyboardRemove()
        elif step == "confirmation":
            text = copy.confirmation(state["time"])
            keyboard = onboarding_reply_keyboard([["Последний шаг"]])
        elif step == "location":
            text, keyboard = copy.LOCATION, ReplyKeyboardRemove()
        else:
            raise ValueError(f"Unknown onboarding step: {step}")
        message = await context.bot.send_message(state["chat_id"], text, parse_mode="HTML", reply_markup=keyboard)
        if step == 'subscription' and isinstance(keyboard, ReplyKeyboardMarkup):
            if any(button.text == 'Продолжить бесплатно' for row in keyboard.keyboard for button in row):
                await _send_onboarding_tariffs(context, state['chat_id'])
    state["screen_id"] = message.message_id
    save_state(state)


async def _transition(context, state, step, *, schedule_time=None):
    state.update(step=step, entered_at=time.time(), reminded=[])
    if step in ("subscription", "schedule_offer") and not state.get("deadline_at"):
        state["deadline_at"] = time.time() + 72 * 3600
    save_state(state, schedule_time=schedule_time)
    await _send_step(context, state)


async def _finish_second_message(context, state):
    async with _lock(context, state["user_id"]):
        latest = load_state(state["user_id"])
        if not latest or latest.get("step") != "location":
            return
        from app.subscription.access import AccessState, current_subscription
        subscription = await asyncio.to_thread(current_subscription, context, latest['user_id'])
        free = subscription is not None and subscription.state(datetime.now().astimezone()) == AccessState.FREE
        if free:
            from app.subscription.free import reply_keyboard
            text, keyboard = copy.COMPLETE_FREE, reply_keyboard()
        else:
            text, keyboard = copy.COMPLETE, get_common_reply_keyboard()
        message = await context.bot.send_message(
            latest["chat_id"], text, parse_mode="HTML", reply_markup=keyboard
        )
        latest.update(step="complete", screen_id=message.message_id, completed_at=time.time())
        save_state(latest, complete=True)
        from data.db import mark_reply_keyboard_version
        mark_reply_keyboard_version(latest["user_id"], COMMON_REPLY_KEYBOARD_VERSION)
        await _start_pending_challenge(context, latest)


async def _finish_job(context):
    state = load_state(context.job.data["user_id"])
    if state and state.get("step") == "location":
        await _finish_second_message(context, state)


async def continue_after_subscription_payment(context, user_id):
    """Resume only the current subscription screen from durable terminal orders."""
    from app.subscription.access import repository_for
    from app.subscription.messages import PAYMENT_FAILED
    repository = repository_for(context, user_id)
    if repository is None:
        return
    async with _lock(context, user_id):
        state = await asyncio.to_thread(load_state, user_id)
        if not state or state.get('step') != 'subscription':
            return
        since = datetime.fromtimestamp(state['entered_at']).astimezone()
        results = await asyncio.to_thread(repository.onboarding_payment_results, user_id, since)
        # A successful retry takes precedence over earlier cancellations.
        successful = [order_id for order_id, status in results if status == 'succeeded']
        if successful:
            if not any([await asyncio.to_thread(repository.notification_sent, user_id,
                                               'payment_success:' + order_id)
                        for order_id in successful]):
                return  # Confirmation must be delivered before the next screen.
            subscription = await asyncio.to_thread(repository.get, user_id)
            if not subscription or not subscription.paid:
                return
            next_state = dict(state, step='schedule_offer', entered_at=time.time(), reminded=[],
                              subscription_paid_period_token=str(int(subscription.paid.starts_at.timestamp())))
            # _send_step persists only after Telegram accepts the screen, so a
            # failed send leaves the subscription screen available for retry.
            await _send_step(context, next_state)
            return
        for order_id, status in results:
            if status != 'canceled':
                continue
            event_key = 'onboarding_payment_canceled:' + order_id
            if await asyncio.to_thread(repository.notification_sent, user_id, event_key):
                continue
            await context.bot.send_message(state['chat_id'], PAYMENT_FAILED, parse_mode='HTML',
                                           reply_markup=_used_subscription_keyboard(context))
            await _send_onboarding_tariffs(context, state['chat_id'])
            await asyncio.to_thread(repository.mark_notification_sent, user_id, event_key,
                                    datetime.now().astimezone())


async def _finish(context, state):
    state["step"] = "location"
    state["reminded"] = []
    save_state(state)
    await _send_step(context, state)
    context.job_queue.run_once(_finish_job, timedelta(seconds=5), data={"user_id": state["user_id"]})


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
    from data.db import clear_user_blocked_if_needed, user_exists
    from app.keyboards import get_restart_confirm_keyboard
    from app.onboarding import START_RESTART_WARNING
    user_id = update.effective_user.id
    just_unblocked = bool(context.user_data.pop("just_unblocked", False))
    was_stale_blocked = clear_user_blocked_if_needed(user_id)
    if just_unblocked or was_stale_blocked:
        await update.effective_message.reply_text(
            "С возвращением 🧡",
            reply_markup=get_common_reply_keyboard(),
        )
        return
    if user_exists(user_id):
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
    next_step = ("subscription" if _subscription_step_enabled(context, state["user_id"])
                 and await _subscription_variant(context, state["user_id"]) != "active"
                 else "schedule_offer")
    await _transition(context, state, next_step)


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
    if step == 'subscription' and text == 'Посмотреть тарифы':
        await _send_step(context, state)
        return True
    # Мягко переносим дальше тех, кто остановился здесь до скрытия шага.
    if step == "subscription" and not _subscription_step_enabled(context, state["user_id"]):
        await _transition(context, state, "schedule_offer")
        return True
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
    if step == "subscription" and text == "Начать 14 дней бесплатно":
        if await _subscription_variant(context, state["user_id"]) == "used":
            await _send_step(context, state)
            return True
        from app.subscription.access import repository_for
        repository = repository_for(context, state["user_id"])
        if repository is not None:
            await asyncio.to_thread(
                repository.begin_fast_trial, state["user_id"], datetime.now().astimezone())
        await _transition(context, state, "schedule_offer")
        return True
    if step == "subscription" and text == "Продолжить бесплатно":
        variant = await _subscription_variant(context, state["user_id"])
        if variant == "used":
            await _finish(context, state)
        elif variant == "active":
            await _transition(context, state, "schedule_offer")
        return True
    if step == "schedule_offer" and text == "Пропустить":
        await _finish(context, state)
        return True
    if step == "schedule_offer" and text == "Настроить расписание":
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
        if state.get("step") == "subscription" and not _subscription_step_enabled(context, state["user_id"]):
            await _transition(context, state, "schedule_offer")
            continue
        if state.get("step") == "location":
            await _finish_second_message(context, state)
            continue
        if state.get("step") in ("complete", "declined"):
            continue
        if state.get("deadline_at") and now >= state["deadline_at"] and state.get("agreement_version") == copy.AGREEMENT_VERSION:
            await _finish(context, state)
            continue
        if state.get("step") in ("time_input", "confirmation"):
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
