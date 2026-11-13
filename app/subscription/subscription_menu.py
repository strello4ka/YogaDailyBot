"""Subscription menu rendering; storage is supplied by the caller."""

import asyncio
from datetime import datetime
from urllib.parse import urlsplit

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from . import messages
from .access import AccessState, Feature, Subscription, has_access
from .runtime import subscription_settings
from .old_users import messages as old_user_messages
from .tariff import MOSCOW


def tariff_keyboard(miniapp_url: str) -> InlineKeyboardMarkup:
    url = urlsplit(miniapp_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Mini App requires a public HTTPS URL without credentials")
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(messages.TARIFF_BUTTON,
                             web_app=WebAppInfo(url=miniapp_url),
                             api_kwargs={"style": "primary"})
    ]])


def optional_tariff_keyboard(miniapp_url: str):
    """The test bot can exercise access states before checkout is connected."""
    return tariff_keyboard(miniapp_url) if miniapp_url else None


def menu_text(subscription: Subscription, now: datetime, *, tariffs_available=True) -> str:
    state = subscription.state(now)
    if state in (AccessState.TRIAL, AccessState.TRIAL_PAID):
        starts_at = (subscription.paid.starts_at if state == AccessState.TRIAL_PAID
                     else subscription.trial.ends_at)
        return messages.trial_status(subscription.trial.days_left(now), starts_at,
                                     purchased=state == AccessState.TRIAL_PAID,
                                     ends_at=(subscription.paid.ends_at
                                              if state == AccessState.TRIAL_PAID else None))
    if state in (AccessState.GIFT, AccessState.GIFT_PAID):
        starts_at = (subscription.paid.starts_at if state == AccessState.GIFT_PAID
                     else subscription.gift.ends_at)
        days_left = max(0, (subscription.gift.ends_at.astimezone(MOSCOW).date()
                            - now.astimezone(MOSCOW).date()).days)
        return old_user_messages.gift_status(
            days_left, starts_at,
            purchased=state == AccessState.GIFT_PAID,
            ends_at=(subscription.paid.ends_at
                     if state == AccessState.GIFT_PAID else None))
    if state == AccessState.PAID:
        return messages.paid_status(subscription.paid.ends_at)
    if tariffs_available:
        return messages.FREE_STATUS
    return messages.FREE_STATUS.replace("\n\nСмотри тарифы ниже 👇", "")


async def send_menu(bot, chat_id: int, subscription: Subscription,
                    now: datetime, miniapp_url: str):
    return await bot.send_message(chat_id=chat_id,
                                  text=menu_text(subscription, now,
                                                 tariffs_available=bool(miniapp_url)),
                                  parse_mode="HTML",
                                  reply_markup=optional_tariff_keyboard(miniapp_url))


def install_subscriptions(application, environment, connection_factory):
    settings = subscription_settings(environment)
    if settings is None:
        return
    from data.subscription_repository import SubscriptionRepository
    from telegram.ext import CallbackQueryHandler, MessageHandler, filters
    from app.payments.config import payment_settings
    payment_config = payment_settings(environment)
    # Production is rejected earlier unless its Mini App URL exists. Test mode
    # may run without checkout; in that case tariff buttons are omitted.
    url = settings.miniapp_url
    repository = SubscriptionRepository(connection_factory, payment_scope=payment_config.scope)
    repository.verify_database(settings.database_name)
    application.bot_data.update(subscription_repository=repository,
                                subscription_allowed_users=settings.allowed_users,
                                subscription_database=settings.database_name,
                                subscription_runtime=settings.runtime,
                                subscription_miniapp_url=url)
    if payment_config.shop_id and settings.miniapp_url:
        from app.payments.service import PaymentService
        provider = payment_config.client()
        try:
            provider.verify_store()
        except Exception:
            provider.close()
            raise
        application.bot_data['subscription_payment_service'] = PaymentService(repository, provider)
    application.add_handler(MessageHandler(filters.ALL & filters.ChatType.PRIVATE, guard_update), group=-6)
    application.add_handler(CallbackQueryHandler(guard_update), group=-6)
    from .jobs import synchronize_access, reconcile_payments, deliver_reminders
    from .payment_wakeup import install as install_payment_wakeup
    install_payment_wakeup(application, connection_factory, settings.database_name)
    application.job_queue.run_repeating(synchronize_access, interval=60, first=1,
                                        name="subscription_access")
    application.job_queue.run_repeating(reconcile_payments, interval=60, first=5,
                                        name='subscription_payments',
                                        job_kwargs={'max_instances': 1, 'coalesce': True})
    application.job_queue.run_repeating(deliver_reminders, interval=60, first=1,
                                        name='subscription_reminders',
                                        job_kwargs={'max_instances': 1, 'coalesce': True})
def requested_feature(text, callback, *, waiting_for_time=False):
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text.strip() else ""
    if command == "/favorite" or callback.startswith("fav_"):
        return Feature.FAVORITES
    if (command == "/schedule" or text.lower() in ("расписание", "изменить время")
            or callback.startswith("schedule_") or (waiting_for_time and not command.startswith("/") and not callback)):
        return Feature.SCHEDULE
    if callback.startswith(("self_", "extra_")):
        return Feature.SELECTION
    if text.lower() in ("🔒 подобрать практику", "подобрать практику", "еще практики", "ещё практики"):
        return Feature.SELECTION
    # Catalog can change through existing configuration; avoid duplicating its labels.
    from app.by_mood.quick_filters import QUICK_FILTERS
    if any(text.casefold() == spec.label.casefold() and spec.slug != "day"
           for spec in QUICK_FILTERS.values()):
        return Feature.SELECTION
    return None


async def guard_update(update, context):
    """Runs before legacy handlers, including callbacks in old messages."""
    from telegram.ext import ApplicationHandlerStop
    from .access import repository_for
    user, chat = update.effective_user, update.effective_chat
    if not user or not chat or chat.type != "private":
        return
    repository = repository_for(context, user.id)
    if repository is None:
        return
    now = datetime.now(MOSCOW)
    state = await asyncio.to_thread(
        repository.synchronize_access, user.id, now)
    message = update.effective_message
    text = (message.text or "") if message else ""
    callback = (update.callback_query.data or "") if update.callback_query else ""
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text.strip() else ""
    url = context.bot_data["subscription_miniapp_url"]
    if command in ("/start", "/change_mode") or callback.startswith("start_restart_"):
        # Preserve the existing restart confirmation and unblock flow.
        return
    if command == "/donate":
        from app.onboarding.state import load_state
        onboarding = load_state(user.id)
        if onboarding and onboarding.get("step") != "complete":
            return  # Existing onboarding guard still applies.
        # A new user may not have a subscription_accounts row yet. The menu is
        # still the free subscription menu, never the removed donations flow.
        await send_menu(context.bot, chat.id, state or Subscription(), now, url)
        raise ApplicationHandlerStop
    if state is None:
        return
    feature = requested_feature(text, callback, waiting_for_time=bool(context.user_data.get("waiting_for_time")))
    if feature and not has_access(state, feature, now):
        # Active challenges are a separate product and remain outside this rollout.
        from data.db import get_user_schedule_settings
        settings = await asyncio.to_thread(get_user_schedule_settings, user.id) or {}
        if feature == Feature.SCHEDULE and settings.get("bot_mode") == "challenge" and settings.get("challenge_start_id"):
            return
        from .free import send_locked
        if update.callback_query:
            await update.callback_query.answer()
        for key in ("waiting_for_time", "waiting_for_schedule_menu_time", "is_time_change"):
            context.user_data.pop(key, None)
        await send_locked(context.bot, chat.id, feature, url)
        raise ApplicationHandlerStop
