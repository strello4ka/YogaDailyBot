"""HTML copy for the one-off old-user transition."""

from datetime import datetime
from html import escape
from urllib.parse import urlsplit

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ..messages import TARIFF_BUTTON
from ..tariff import last_access_date


SUBSCRIPTION_DETAILS_BUTTON = "Что входит в подписку?"
FREE_DETAILS_BUTTON = "Что останется бесплатным?"
SUBSCRIPTION_DETAILS_CALLBACK = "old_users:subscription_details"
FREE_DETAILS_CALLBACK = "old_users:free_details"


def first_message(gift_ends: datetime) -> str:
    """Render the approved launch message for users from the frozen cohort."""
    access_until = last_access_date(gift_ends)
    return (
        "<b>Если ты читаешь это,\n"
        "поздравляю, ты — легенда\n"
        "YogaDailyBot 🧡</b>\n\n"
        "Мы познакомились, когда я только учился подбирать практики, "
        "иногда путался в кнопках и мечтал стать большим ботом для здорового тела.\n\n"
        "Благодаря тебе я вырос и готов к новому этапу: в YogaDailyBot "
        "<b>появляется подписка.</b>\n\n"
        "Конечно, я подготовил <b>подарки для своих:</b>\n"
        "<blockquote>"
        f"• До <b>{access_until:%d.%m.%Y}</b> для тебя ничего не изменится, потому что у тебя "
        "есть <b>30 дней полного доступа бесплатно.</b>\n"
        "• Для тебя действуют <b>специальные цены</b> на все тарифы подписки</blockquote>\n\n"
        "Я ещё напомню, когда подарочный период будет заканчиваться, но купить подписку "
        "можно уже сейчас, она начнёт действовать <b>после подарочного периода</b> 👇"
    )


def gift_three_days(name: str, gift_ends: datetime, offer_ends: datetime) -> str:
    """Render the approved three-day reminder for the gift period."""
    access_until = last_access_date(gift_ends)
    special_prices_until = last_access_date(offer_ends)
    greeting = f"<b>{escape(name)}</b>, " if name else ""
    return (
        "⏳ <b>Подарочный период заканчивается через 3 дня</b>\n\n"
        f"{greeting}до <b>{access_until:%d.%m.%Y}</b> тебе доступны все возможности YogaDailyBot.\n\n"
        "После этого расписание, все фильтры по практикам и избранное станут недоступны "
        "без подписки. Бесплатно останутся: «Практика дня» и твой прогресс.\n\n"
        "<b>Только для своих действуют специальные цены на все тарифы "
        f"до {special_prices_until:%d.%m.%Y} 🧡</b>\n\n"
        "Ты можешь оплатить подписку сейчас, а начнётся она через 3 дня 👇"
    )


def gift_last_day() -> str:
    """Render the approved reminder for the final gift-access day."""
    return (
        "⏳ <b>Сегодня последний день подарочного периода</b>\n\n"
        "Уже завтра станут недоступны:\n"
        "🌀 подборы практик по настроению\n"
        "🌀 настройка длительности, сложности и направления\n"
        "🌀 автоматическая рассылка по расписанию\n"
        "🌀 избранные практики\n\n"
        "Бесплатно останутся: «Практика дня» и твой прогресс."
    )


def gift_expired(offer_ends: datetime) -> str:
    """Render the approved transition from gift access to free mode."""
    special_prices_until = last_access_date(offer_ends)
    return (
        "<b>Подарочный месяц завершился 🧡</b>\n\n"
        "Теперь ты в бесплатной версии YogaDailyBot:\n"
        "🌀 Практика дня\n"
        "🌀 Прогресс\n\n"
        "Твои настройки и избранные практики сохранены — они снова станут доступны после "
        "оформления подписки.\n\n"
        "Только для своих действуют специальные цены на все тарифы до "
        f"<b>{special_prices_until:%d.%m.%Y}</b>.\n"
        "Управлять подпиской можно в любой момент в <b>Меню</b> ↙️"
    )


def gift_subscription_activated(name: str, ends_at: datetime) -> str:
    """Confirm activation of a subscription purchased during gift access."""
    greeting = (f"{escape(name)}, рад, что ты остаешься со мной 🧡"
                if name else "Рад, что ты остаешься со мной 🧡")
    return (
        "✅ <b>Подписка активна</b>\n\n"
        "Подарочный месяц завершился, и с сегодняшнего дня начала действовать твоя подписка.\n"
        f"Она действует до <b>{last_access_date(ends_at):%d.%m.%Y}</b>.\n\n"
        "Все возможности YogaDailyBot остаются доступны 🧡\n"
        "Управлять подпиской можно в <b>Меню</b> ↙️\n\n"
        + greeting
    )


def special_prices_seven_days(offer_ends: datetime) -> str:
    """Render the calm midpoint reminder for an unused special offer."""
    special_prices_until = last_access_date(offer_ends)
    return (
        "Для тебя всё ещё действуют <b>специальные цены</b> для самых первых "
        "пользователей 🧡\n\n"
        f"Предложение доступно до <b>{special_prices_until:%d.%m.%Y}</b>"
    )


def special_prices_three_days() -> str:
    """Render the approved price-focused reminder three days before expiry."""
    return (
        "⏳ <b>Специальные цены исчезнут через 3 дня</b>\n\n"
        "Только для олдов:\n"
        "<b>1 месяц:</b> 350 ₽ → <b>250 ₽</b>\n"
        "<b>3 месяца:</b> 800 ₽ → <b>600 ₽</b>\n"
        "<b>6 месяцев:</b> 1 400 ₽ → <b>1 000 ₽</b>\n"
        "<b>1 год:</b> 2 500 ₽ → <b>1 800 ₽</b>\n\n"
        "Выбирай любой тариф 👇"
    )


def special_prices_last_day() -> str:
    """Render the approved final reminder on the last special-price day."""
    return (
        "⏳ <b>Сегодня последний день специальных цен</b>\n\n"
        "Уже завтра для тебя будут такие же цены, как для всех.\n"
        "Если ты любишь запрыгивать в последний вагон, то момент настал!\n\n"
        "Предложение действует до конца сегодняшнего дня 👇"
    )


def tariff_button_keyboard(miniapp_url: str) -> InlineKeyboardMarkup:
    """Build the single tariff button used by old-user reminders."""
    url = urlsplit(miniapp_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Mini App requires a public HTTPS URL without credentials")
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐ " + TARIFF_BUTTON,
                             web_app=WebAppInfo(url=miniapp_url),
                             api_kwargs={"style": "primary"})
    ]])


def first_message_keyboard(miniapp_url: str) -> InlineKeyboardMarkup:
    """Build the approved three-row keyboard for the launch message."""
    url = urlsplit(miniapp_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Mini App requires a public HTTPS URL without credentials")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TARIFF_BUTTON,
                              web_app=WebAppInfo(url=miniapp_url),
                              api_kwargs={"style": "primary"})],
        [InlineKeyboardButton(SUBSCRIPTION_DETAILS_BUTTON,
                              callback_data=SUBSCRIPTION_DETAILS_CALLBACK)],
        [InlineKeyboardButton(FREE_DETAILS_BUTTON,
                              callback_data=FREE_DETAILS_CALLBACK)],
    ])
