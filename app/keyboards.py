"""Telegram keyboards for YogaDailyBot.
Contains all inline keyboards used in the bot interface.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# Текст выбора режима: /change_mode и после выхода из челленджа.
MODE_CHOICE_INTRO_MARKDOWN = (
    "*Выбери режим работы бота:*\n\n"
    "🌀 Режим *Daily* — для тех, кто хочет мягко внедрить привычку заниматься ежедневно и не перегорать.\n"
    "*Выбираешь удобное время, и бот присылает практику в это время каждый день.*\n"
    "Неделя содержит сбалансированный набор практик:\n"
    "• 2-3 бодрые, 5-15 минут\n"
    "• по вторникам - всегда работа с осанкой, спиной и шеей\n"
    "• по пятницам - что-то необычное для развития кругозора и получения нового опыта\n"
    "• по субботам - горячая активная, 20-25 минут\n"
    "• по воскресеньям - релакс, 20-25 минут\n"
    "• плюс бонус - приходит один раз в неделю в дополнение к основной практике: дыхательная техника, медитация, отстройка асан, изучение балансов на руках.\n"
    "*Ты не заметишь напряга, но тело скажет \"спасибо\" и отблагодарит отражением в зеркале!*\n\n"
    "🌀 Режим *By mood* — для тех, кто хочет делать зарядки и разминки по состоянию \"здесь и сейчас\", но без траты времени на поиск качественного контента.\n"
    "*Нажимаешь кнопку по настроению, и бот сразу подбирает подходящую практику под твой запрос*: \"Ленивые дни\", \"Пятиминутка\", \"Практика дня\" и т.д. Также можно самому настроить время и интенсивность.\n\n"
    "Оба режима помогают практиковать регулярно, просто разным способом:\n"
    "*Daily* — через привычку и стабильность\n"
    "*By mood* — через гибкость и свободу выбора.\n\n"
    "Выбирай то, что ближе тебе сейчас, и *жми кнопку* 👇 \n"
    "(изменить режим можно в любой момент в меню)"
)


def get_mode_choice_keyboard():
    """Inline: выбор режима после /start или /change_mode."""
    keyboard = [
        [
            InlineKeyboardButton("Daily", callback_data="mode_pick_daily"),
            InlineKeyboardButton("By mood", callback_data="mode_pick_by_mood"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_start_onboarding_keyboard():
    """Первый экран /start: пример практики или переход к выбору режима."""
    keyboard = [
        [InlineKeyboardButton("Посмотреть пример", callback_data="onboarding_show_example")],
        [InlineKeyboardButton("Выбрать режим", callback_data="onboarding_open_mode_choice")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_choose_mode_keyboard():
    """Кнопка под примером практики для перехода к выбору режима."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Выбрать режим", callback_data="onboarding_open_mode_choice")]]
    )


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
    """Reply-клавиатура режима Daily и Challenge: время, советы, пауза, доп. практики."""
    keyboard = [
        [KeyboardButton("Изменить время"), KeyboardButton("Советы")],
        [KeyboardButton("Пауза")],
        [KeyboardButton("Еще практики")],
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
            KeyboardButton("Практика дня"),
            KeyboardButton("Без коврика"),
        ],
        [
            KeyboardButton("Ленивые дни"),
            KeyboardButton("Пятиминутка"),
        ],
        [
            KeyboardButton("Хард"),
            KeyboardButton("Сам решу"),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )
