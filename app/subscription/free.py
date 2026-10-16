"""Free-mode UI. It never deletes favorites or overwrites schedule settings."""

from telegram import ReplyKeyboardMarkup

from . import messages
from .access import Feature
from .subscription_menu import optional_tariff_keyboard


def reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["Практика дня"], ["🔒 Подобрать практику"]],
                               resize_keyboard=True, one_time_keyboard=False)


def locked_text(feature: Feature) -> str:
    return {
        Feature.FAVORITES: messages.FAVORITES_LOCKED,
        Feature.SCHEDULE: messages.SCHEDULE_LOCKED,
        Feature.SELECTION: messages.SELECTION_LOCKED,
    }[Feature(feature)]


async def send_locked(bot, chat_id: int, feature: Feature, miniapp_url: str):
    return await bot.send_message(chat_id=chat_id, text=locked_text(feature),
                                  parse_mode="HTML", reply_markup=optional_tariff_keyboard(miniapp_url))
