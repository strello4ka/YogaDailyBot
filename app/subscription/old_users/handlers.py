"""Callbacks used by the one-off old-user launch message."""

from app.handlers.help import FREE_MODE_FAQ_TEXT, SUBSCRIPTION_FAQ_TEXT

from .messages import FREE_DETAILS_CALLBACK, SUBSCRIPTION_DETAILS_CALLBACK


async def access_details_callback(update, context):
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()
    text = {
        SUBSCRIPTION_DETAILS_CALLBACK: SUBSCRIPTION_FAQ_TEXT,
        FREE_DETAILS_CALLBACK: FREE_MODE_FAQ_TEXT,
    }.get(query.data)
    if text:
        await query.message.reply_text(text)
