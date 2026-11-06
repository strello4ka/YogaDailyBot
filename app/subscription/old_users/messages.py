"""HTML copy for the one-off old-user transition."""

from datetime import datetime
from html import escape
from typing import Optional
from urllib.parse import urlsplit

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ..messages import TARIFF_BUTTON
from ..tariff import last_access_date, local_time


SUBSCRIPTION_DETAILS_BUTTON = "Что входит в подписку?"
FREE_DETAILS_BUTTON = "Что останется бесплатным?"
SUBSCRIPTION_DETAILS_CALLBACK = "old_users:subscription_details"
FREE_DETAILS_CALLBACK = "old_users:free_details"
FEEDBACK_CALLBACK = "old_users:feedback"
FEEDBACK_INPUT_PROMPT = "Напиши сюда любой текст"
FEEDBACK_SAVE_ERROR = "Не получилось сохранить сообщение. Попробуй ещё раз."
FEEDBACK_THANK_YOU = (
    "Спасибо за твою обратную связь!"
)


def _offer_last_date(value: datetime):
    """Inclusive date for both midnight production and minute-based test deadlines."""
    local = local_time(value)
    has_clock_time = any((local.hour, local.minute, local.second, local.microsecond))
    return local.date() if has_clock_time else last_access_date(local)


def _days_word(value: int) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return "день"
    elif value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14):
        return "дня"
    return "дней"


def _days_label(value: int) -> str:
    return f"{value} {_days_word(value)}"


def gift_status(days_left: int, starts_at: datetime, purchased: bool = False,
                ends_at: Optional[datetime] = None) -> str:
    """Render the temporary gift-access state shown in the subscription menu."""
    if purchased:
        if ends_at is None:
            raise ValueError("Paid subscription end is required")
        return ("<b>🎁 У тебя сейчас подарочный период</b>\n\n"
                f"Осталось <b>{days_left}</b> {_days_word(days_left)}\n\n"
                "Ты уже оформил подписку, она начнет действовать после окончания "
                "подарочного периода с "
                f"<b>{local_time(starts_at):%d.%m.%Y}</b> по "
                f"<b>{last_access_date(ends_at):%d.%m.%Y}</b>")
    return ("<b>🎁 У тебя сейчас подарочный период</b>\n\n"
            "Полный доступ ко всем возможностям YogaDailyBot действует еще "
            f"<b>{_days_label(days_left)}</b>\n\n"
            "Ты можешь оформить подписку в любой момент, она начнет действовать с "
            f"<b>{local_time(starts_at):%d.%m.%Y}</b>")


def first_message(gift_ends: datetime) -> str:
    """Render the approved launch message for users from the frozen cohort."""
    access_until = _offer_last_date(gift_ends)
    return (
        "<b>Если ты читаешь это,поздравляю, ты — легенда YogaDailyBot 🧡</b>\n\n"
        "Когда мы познакомились, я только учился подбирать практики, "
        "иногда путался в кнопках и мечтал стать большим ботом для здорового тела.\n\n"
        "Благодаря тебе я вырос и готов к новому этапу:\n"
        "<b>в YogaDailyBot появляется подписка.</b>\n\n"
        "Конечно, я подготовил <b>подарки для своих:</b>\n"
        "<blockquote>"
        f"• До <b>{access_until:%d.%m.%Y}</b> для тебя ничего не изменится, потому что у тебя "
        "есть <b>30 дней полного доступа бесплатно.</b>\n"
        "• Для тебя действуют <b>специальные цены</b> на все тарифы подписки</blockquote>\n\n"
        "Я ещё напомню, когда подарочный период будет заканчиваться, но купить подписку "
        "можно уже сейчас, она начнёт действовать <b>после подарочного периода</b> 👇"
    )


def feedback_message() -> str:
    """Ask the frozen launch cohort for feedback after the announcement."""
    return (
        "С началом нового этапа мне особенно важно узнать твоё мнение. "
        "Расскажи, что тебе нравится, чего не хватает и что стоит улучшить.\n\n"
        "<b>Спасибо, что помогаешь мне расти 🧡</b>"
    )


def feedback_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Поделиться мнением", callback_data=FEEDBACK_CALLBACK,
                             api_kwargs={"style": "primary"})
    ]])


def gift_three_days(name: str, gift_ends: datetime, offer_ends: datetime) -> str:
    """Render the approved three-day reminder for the gift period."""
    access_until = _offer_last_date(gift_ends)
    special_prices_until = _offer_last_date(offer_ends)
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
    return (
        "<b>Подарочный месяц завершился 🧡</b>\n\n"
        "Теперь ты в бесплатной версии YogaDailyBot.\n"
        "Твои избранные практики сохранены, они снова станут доступны после "
        "оформления подписки."
    )


def gift_expired_tariff_prompt(offer_ends: datetime) -> str:
    """Render the separate tariff prompt sent after gift access expires."""
    special_prices_until = _offer_last_date(offer_ends)
    return (
        "<b>Только для своих</b> действуют специальные цены на все тарифы до "
        f"<b>{special_prices_until:%d.%m.%Y}</b>."
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
    )


def special_prices_seven_days(offer_ends: datetime) -> str:
    """Render the calm midpoint reminder for an unused special offer."""
    special_prices_until = _offer_last_date(offer_ends)
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
        "1 месяц: 350 ₽ → 250 ₽\n"
        "3 месяца: 800 ₽ → 600 ₽\n"
        "6 месяцев: 1 400 ₽ → 1 000 ₽\n"
        "1 год: 2 500 ₽ → 1 800 ₽\n\n"
        "Выбирай любой тариф 👇"
    )


def special_prices_last_day() -> str:
    """Render the approved final reminder on the last special-price day."""
    return (
        "⏳ <b>Сегодня последний день специальных цен</b>\n\n"
        "Уже завтра для тебя будут такие же цены, как для всех.\n"
        "Если ты любишь запрыгивать в последний вагон, то момент настал!"
    )


def reminder_text(kind, name, gift_ends, offer_ends):
    """Keep temporary notification copy out of the permanent reminder worker."""
    if kind == 'launch':
        return first_message(gift_ends)
    if kind == 'launch_feedback':
        return feedback_message()
    if kind == 'gift_three_days':
        return gift_three_days(name, gift_ends, offer_ends)
    if kind == 'gift_expired':
        return gift_expired(offer_ends)
    if kind == 'special_prices_seven_days':
        return special_prices_seven_days(offer_ends)
    renderers = {'gift_last_day': gift_last_day,
                 'special_prices_three_days': special_prices_three_days,
                 'special_prices_last_day': special_prices_last_day}
    return renderers[kind]()


def tariff_button_keyboard(miniapp_url: str) -> InlineKeyboardMarkup:
    """Build the single tariff button used by old-user reminders."""
    url = urlsplit(miniapp_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Mini App requires a public HTTPS URL without credentials")
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(TARIFF_BUTTON,
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
        [InlineKeyboardButton(FREE_DETAILS_BUTTON,
                              callback_data=FREE_DETAILS_CALLBACK)],
        [InlineKeyboardButton(SUBSCRIPTION_DETAILS_BUTTON,
                              callback_data=SUBSCRIPTION_DETAILS_CALLBACK)],
    ])
