"""Telegram keyboards for YogaDailyBot.
Contains all inline keyboards used in the bot interface.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def get_welcome_keyboard():
    """Создает клавиатуру для приветственного сообщения.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопкой "Выбрать время"
    """
    keyboard = [
        [InlineKeyboardButton("Выбрать время", callback_data="want_start")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_practice_done_keyboard():
    """Клавиатура с кнопкой «✔️Я сделал!» под сообщением с практикой.
    
    Returns:
        InlineKeyboardMarkup: Одна кнопка «✔️Я сделал!» (callback_data="practice_done")
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✔️Я сделал!", callback_data="practice_done")]
    ])


def get_main_reply_keyboard():
    """Создает главную Reply-клавиатуру с основными функциями бота.
    
    Кнопки:
    - Изменить время
    - Предложить практику
    - Советы
    - Донаты
    - Мой прогресс
    
    Returns:
        ReplyKeyboardMarkup: Reply-клавиатура с основными функциями
    """
    keyboard = [
        [KeyboardButton("Изменить время"), KeyboardButton("Предложить практику")],
        [KeyboardButton("Советы"), KeyboardButton("Донаты")],
        [KeyboardButton("Мой прогресс")]
    ]
    return ReplyKeyboardMarkup(
        keyboard, 
        resize_keyboard=True,  # Автоматически подгоняет размер кнопок
        one_time_keyboard=False  # Клавиатура остается после нажатия
    )
