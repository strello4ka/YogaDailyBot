"""Compatibility fallback for the subscription command."""

from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes


async def handle_donations_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Never revive the removed donations flow when subscription guard is absent."""
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()

    context.user_data.pop('waiting_for_practice_suggestion', None)
    miniapp_url = context.bot_data.get("subscription_miniapp_url", "")
    if miniapp_url:
        from app.subscription.access import Subscription
        from app.subscription.subscription_menu import send_menu
        from app.subscription.tariff import MOSCOW
        await send_menu(
            context.bot,
            update.effective_chat.id,
            Subscription(),
            datetime.now(MOSCOW),
            miniapp_url,
        )
        return

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Не удалось загрузить данные о подписке. Попробуй немного позже.",
    )


async def handle_legacy_donation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop buttons in already sent legacy donation messages."""
    await update.callback_query.answer(
        "Этот способ поддержки больше недоступен. Открой раздел «Подписка».",
        show_alert=True,
    )
