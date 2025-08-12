"""Telegram keyboards for YogaDailyBot.
Contains all inline keyboards used in the bot interface.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_welcome_keyboard():
    """Создает клавиатуру для приветственного сообщения.
    
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопкой "Выбрать время"
    """
    keyboard = [
        [InlineKeyboardButton("Выбрать время", callback_data="want_start")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_keyboard():
    """Создает главное меню бота с 5 кнопками.
    
    Кнопки:
    - Изменить время
    - Начать сначала  
    - Предложить практику
    - Помощь
    - Донаты
    
    Returns:
        InlineKeyboardMarkup: Главное меню
    """
    keyboard = [
        [InlineKeyboardButton("Изменить время", callback_data="change_time")],
        [InlineKeyboardButton("Начать сначала", callback_data="reset")],
        [InlineKeyboardButton("Предложить практику", callback_data="suggest_practice")],
        [InlineKeyboardButton("Помощь", callback_data="help")],
        [InlineKeyboardButton("Донаты", callback_data="donations")]
    ]
    return InlineKeyboardMarkup(keyboard)
