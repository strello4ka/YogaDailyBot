"""Subscription menu rendering; storage is supplied by the caller."""

import asyncio
from datetime import datetime
from math import ceil
from urllib.parse import urlsplit
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from . import messages
from .access import AccessState, Feature, Subscription, has_access
from .demo import is_fast_trial
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
        if is_fast_trial(subscription.trial):
            remaining = max(0, ceil((subscription.trial.ends_at - now).total_seconds() / 60))
            return ("🧪 Ускоренный пробный период для тестового бота\n\n"
                    f"Осталось около {remaining} мин. После окончания включится бесплатный режим.")
        starts_at = (subscription.paid.starts_at if state == AccessState.TRIAL_PAID
                     else subscription.trial.ends_at)
        return messages.trial_status(subscription.trial.days_left(now), starts_at,
                                     purchased=state == AccessState.TRIAL_PAID)
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


def test_settings(environment):
    """Require the explicit test flag, env file and isolated database settings."""
    if environment.get("SUBSCRIPTION_TEST_ENABLED", "").lower() != "true":
        return None
    test_env = Path(__file__).resolve().parents[2] / "test" / ".env.test"
    if Path(environment.get("ENV_FILE", "")).resolve() != test_env:
        raise ValueError("Subscriptions may only run with the project's test/.env.test")
    bot_id, separator, token_secret = environment.get("BOT_TOKEN", "").partition(":")
    if not separator or not bot_id.isdigit() or not token_secret:
        raise ValueError("BOT_TOKEN must contain a numeric bot ID and token secret")
    # Telegram tokens do not identify a bot as test or production. Isolation here
    # comes from the explicit flag, exact env-file path and dedicated database.
    # An empty allowlist enables the feature for every user in that environment.
    raw_users = environment.get("SUBSCRIPTION_TEST_USERS", "").strip()
    users = (frozenset(int(value.strip()) for value in raw_users.split(",") if value.strip())
             if raw_users else None)
    if users is not None and (not users or any(user_id <= 0 for user_id in users)):
        raise ValueError("Test user IDs must be positive")
    url = environment.get("SUBSCRIPTION_MINIAPP_URL", "")
    if url:
        tariff_keyboard(url)
    database_name = environment.get("SUBSCRIPTION_TEST_DATABASE", "")
    if database_name != 'yogadaily_test':
        raise ValueError("Subscriptions require the isolated yogadaily_test database")
    return users, url, database_name


def install_test_subscriptions(application, environment, connection_factory):
    settings = test_settings(environment)
    if settings is None:
        return
    from data.subscription_repository import SubscriptionRepository
    from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters
    users, configured_url, database_name = settings
    from app.payments.config import payment_settings
    payment_config = payment_settings(environment)
    # Trial reminders can always show the existing tariff preview. Real test
    # checkout is enabled only with an explicitly configured Mini App URL.
    from app.handlers.donations import MINIAPP_PREVIEW_URL
    url = configured_url or MINIAPP_PREVIEW_URL
    repository = SubscriptionRepository(connection_factory, payment_scope=payment_config.scope)
    repository.verify_test_database(database_name)
    application.bot_data.update(subscription_repository=repository,
                                subscription_test_users=users, subscription_miniapp_url=url)
    expiry_user = environment.get('SUBSCRIPTION_TEST_PAID_EXPIRY_USER', '')
    expiry_end = environment.get('SUBSCRIPTION_TEST_PAID_EXPIRY_END', '')
    if expiry_user or expiry_end:
        user_id = int(expiry_user)
        end = datetime.fromisoformat(expiry_end)
        if user_id <= 0 or end.utcoffset() is None or (users is not None and user_id not in users):
            raise ValueError('An allowed test user and timezone-aware expiry are required')
        application.bot_data['subscription_test_paid_expiry'] = (user_id, end)
    if payment_config.shop_id and configured_url:
        from app.payments.service import PaymentService
        provider = payment_config.client()
        try:
            provider.verify_store()
        except Exception:
            provider.close()
            raise
        application.bot_data['subscription_payment_service'] = PaymentService(
            repository, provider, allowed_tariffs=('month',) if payment_config.live else None)
    application.add_handler(MessageHandler(filters.ALL & filters.ChatType.PRIVATE, guard_update), group=-6)
    application.add_handler(CallbackQueryHandler(guard_update), group=-6)
    application.add_handler(CallbackQueryHandler(restore_schedule_callback,
                                                pattern=r"^subscription_restore:(yes|no):[0-9]+$"))
    application.add_handler(CommandHandler("subscription_test", subscription_test_command))
    application.add_handler(CallbackQueryHandler(subscription_test_start_callback,
                                                pattern=r"^subscription_test_start$"))
    from .jobs import synchronize_test_access, reconcile_test_payments, deliver_test_reminders
    from .payment_wakeup import install as install_payment_wakeup
    install_payment_wakeup(application, connection_factory)
    application.job_queue.run_repeating(synchronize_test_access, interval=60, first=1,
                                        name="subscription_test_access")
    application.job_queue.run_repeating(reconcile_test_payments, interval=60, first=5,
                                        name='subscription_test_payments',
                                        job_kwargs={'max_instances': 1, 'coalesce': True})
    application.job_queue.run_repeating(deliver_test_reminders, interval=10, first=1,
                                        name='subscription_test_reminders',
                                        job_kwargs={'max_instances': 1, 'coalesce': True})


async def subscription_test_command(update, context):
    """Offer a replayable short trial only through the isolated test-bot menu."""
    from .access import repository_for
    repository = repository_for(context, update.effective_user.id)
    if repository is None:
        return
    current = await asyncio.to_thread(repository.get, update.effective_user.id)
    if current is not None:
        await send_menu(context.bot, update.effective_chat.id, current, datetime.now(MOSCOW),
                        context.bot_data['subscription_miniapp_url'])
    await update.effective_message.reply_text(
        "🧪 Ускоренный тест: проба 15 минут. Через 10 минут придёт первое напоминание, "
        "через 14 — второе, через 15 — сообщение о бесплатном режиме. "
        "Ещё через 2 минуты придёт напоминание после пробы. "
        "Повторный запуск начнёт тест заново только для твоего аккаунта в тестовом боте.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Запустить тест", callback_data="subscription_test_start")
        ]]))


async def subscription_test_start_callback(update, context):
    from .access import repository_for
    query = update.callback_query
    repository = repository_for(context, update.effective_user.id)
    if repository is None:
        await query.answer()
        return
    from app.keyboards import get_common_reply_keyboard
    now = datetime.now(MOSCOW)
    try:
        subscription = await asyncio.to_thread(
            repository.begin_fast_trial, update.effective_user.id, now, replay=True)
    except ValueError:
        await query.answer("У аккаунта уже есть оплаченный период или платёжный заказ.", show_alert=True)
        return
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(update.effective_chat.id,
        "Ускоренный пробный период начался 🧡 Полный доступ — 15 минут.",
        reply_markup=get_common_reply_keyboard())
    await send_menu(context.bot, update.effective_chat.id, subscription, now,
                    context.bot_data['subscription_miniapp_url'])


def requested_feature(text, callback, *, waiting_for_time=False):
    command = text.split(maxsplit=1)[0].split("@", 1)[0].lower() if text.strip() else ""
    if command == "/favorite" or callback.startswith("fav_"):
        return Feature.FAVORITES
    if (command == "/schedule" or text.lower() in ("расписание", "изменить время", "пауза")
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
    if not user or not chat or chat.type != "private" or repository_for(context, user.id) is None:
        return
    now = datetime.now(MOSCOW)
    state = await asyncio.to_thread(
        repository_for(context, user.id).synchronize_access, user.id, now)
    if state is None:
        return
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
        await send_menu(context.bot, chat.id, state, now, url)
        raise ApplicationHandlerStop
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


async def offer_schedule_restore(bot, chat_id, saved_time, period_token):
    """Payment completion may call this only for a purchase from free mode."""
    from app.onboarding.messages import SCHEDULE_OFFER
    text = (messages.restore_schedule(saved_time) if saved_time not in (None, '', '00:00')
            else SCHEDULE_OFFER)
    return await bot.send_message(chat_id, text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Да", callback_data="subscription_restore:yes:{}".format(period_token)),
            InlineKeyboardButton("Не сейчас", callback_data="subscription_restore:no:{}".format(period_token)),
        ]]))


async def restore_schedule_callback(update, context):
    from .access import repository_for
    query = update.callback_query
    repository = repository_for(context, update.effective_user.id)
    if repository is None:
        await query.answer()
        return
    _, choice, period_token = query.data.split(':', 2)
    now = datetime.now(MOSCOW)
    outcome = await asyncio.to_thread(
        repository.resolve_restore, update.effective_user.id, period_token, now,
        choice == 'yes')
    if outcome == 'stale':
        await query.answer("Это предложение уже неактуально.", show_alert=True)
        return
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)
    if outcome == 'restored':
        await query.message.reply_text("Расписание восстановлено 🧡 Практики начнут приходить с завтрашнего дня.")
    elif outcome == 'setup':
        from app.handlers.schedule import send_schedule_time_prompt
        await send_schedule_time_prompt(update, context)
