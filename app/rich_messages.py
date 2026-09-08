"""Совместимость PTB 22.3 с Rich Messages Bot API 10.3.

Схемы: https://core.telegram.org/bots/api#sendrichmessage
Один адаптер использует существующий транспорт бота, без отдельного HTTP-клиента.
"""

from telegram import Message


def paragraph(text):
    return {"type": "paragraph", "text": text}


def button_row(buttons):
    return {"type": "buttons", "buttons": buttons}


async def send_rich_message(bot, chat_id, blocks, *, reply_markup=None):
    result = await bot._post("sendRichMessage", {
        "chat_id": chat_id,
        "rich_message": {"blocks": blocks},
        "reply_markup": reply_markup,
    })
    return Message.de_json(result, bot)


async def edit_rich_message(bot, chat_id, message_id, blocks):
    return await bot._post("editMessageText", {
        "chat_id": chat_id, "message_id": message_id,
        "rich_message": {"blocks": blocks},
    })
