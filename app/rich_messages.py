"""Thin Bot API 10.3 adapter for Telegram Rich Messages."""

from telegram import Message


def paragraph(text):
    return {"type": "paragraph", "text": text}


def button_row(buttons):
    return {"type": "buttons", "buttons": buttons}


async def send_rich_message(bot, chat_id, blocks, *, reply_markup=None):
    payload = {"chat_id": chat_id, "rich_message": {"blocks": blocks}}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
    result = await bot._post("sendRichMessage", payload)
    return Message.de_json(result, bot)


async def edit_rich_message(bot, chat_id, message_id, blocks):
    return await bot._post("editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "rich_message": {"blocks": blocks},
    })
