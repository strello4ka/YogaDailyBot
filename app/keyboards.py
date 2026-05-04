"""Telegram keyboards for YogaDailyBot.
Contains all inline keyboards used in the bot interface.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def get_mode_choice_keyboard():
    """Inline: выбор режима после /start или /change_mode."""
    keyboard = [
        [
            InlineKeyboardButton("Daily", callback_data="mode_pick_daily"),
            InlineKeyboardButton("By mood", callback_data="mode_pick_by_mood"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_welcome_keyboard():
    """Клавиатура после выбора Daily: кнопка «Выбрать время»."""
    keyboard = [
        [InlineKeyboardButton("Выбрать время", callback_data="want_start")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_practice_done_keyboard():
    """Клавиатура с кнопкой «✅ Я сделал!» под сообщением с практикой.
    
    Returns:
        InlineKeyboardMarkup: Одна кнопка «✅ Я сделал!» (callback_data="practice_done")
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Я сделал!", callback_data="practice_done")]
    ])


def get_main_reply_keyboard():
    """Reply-клавиатура режима Daily: время, советы, пауза рассылки."""
    keyboard = [
        [KeyboardButton("Изменить время"), KeyboardButton("Советы")],
        [KeyboardButton("Пауза")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_by_mood_reply_keyboard():
    """Reply-клавиатура режима By mood: фильтры по запросу."""
    keyboard = [
        [
            KeyboardButton("практика дня"),
            KeyboardButton("без коврика"),
        ],
        [
            KeyboardButton("ленивые дни"),
            KeyboardButton("пятиминутка"),
        ],
        [
            KeyboardButton("хард"),
            KeyboardButton("сам решу"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )
