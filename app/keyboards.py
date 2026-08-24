"""Telegram keyboards for YogaDailyBot.
Contains all inline keyboards used in the bot interface.
"""

from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

from app.by_mood.quick_filters import get_active_quick_filters
from app.practice_ref import format_practice_callback


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


def get_restart_confirm_keyboard():
    """Подтверждение повторного /start: полный сброс прогресса и избранного."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Да, перезапустить", callback_data="start_restart_yes")],
        [InlineKeyboardButton("Нет", callback_data="start_restart_no")],
    ])


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


def get_practice_action_keyboard(
    practice_id: int,
    is_favorited: bool,
    practice_catalog: str = "yoga",
) -> InlineKeyboardMarkup:
    """Клавиатура под практикой: избранное + «✅ Я сделал!»."""
    favorite_label = "🧡 Убрать" if is_favorited else "🧡 В избранное"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                favorite_label,
                callback_data=format_practice_callback("fav_toggle", practice_id, practice_catalog),
            ),
            InlineKeyboardButton(
                "✅ Я сделал!",
                callback_data=format_practice_callback("practice_done", practice_id, practice_catalog),
            ),
        ]
    ])


def get_practice_favorite_keyboard(
    practice_id: int,
    is_favorited: bool,
    practice_catalog: str = "yoga",
) -> InlineKeyboardMarkup:
    """Только кнопка избранного (после «Я сделал!» или новой практики)."""
    favorite_label = "🧡 Убрать" if is_favorited else "🧡 В избранное"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                favorite_label,
                callback_data=format_practice_callback("fav_toggle", practice_id, practice_catalog),
            )
        ],
    ])


def practice_id_from_action_markup(reply_markup: Optional[InlineKeyboardMarkup]) -> Optional[int]:
    """practice_id из кнопок fav_toggle / practice_done под практикой."""
    if not reply_markup or not reply_markup.inline_keyboard:
        return None
    for row in reply_markup.inline_keyboard:
        for btn in row:
            data = btn.callback_data or ""
            if data.startswith(("fav_toggle:", "practice_done:")):
                from app.practice_ref import practice_id_from_callback_data
                return practice_id_from_callback_data(data)
    return None


def message_has_done_button(reply_markup: Optional[InlineKeyboardMarkup]) -> bool:
    if not reply_markup or not reply_markup.inline_keyboard:
        return False
    for row in reply_markup.inline_keyboard:
        for btn in row:
            if (btn.callback_data or "").startswith("practice_done:"):
                return True
    return False


def get_favorites_carousel_keyboard(
    practice_id: int,
    is_favorited: bool,
    index: int,
    total: int,
    practice_catalog: str = "yoga",
    *,
    show_done: bool = True,
) -> InlineKeyboardMarkup:
    """Карусель избранного: действия с практикой + навигация.

    show_done=False — после отметки или на следующий день (кнопка «Я сделал!» снята).
    """
    favorite_label = "🧡 Убрать" if is_favorited else "🧡 В избранное"
    action_row = [
        InlineKeyboardButton(
            favorite_label,
            callback_data=format_practice_callback("fav_toggle", practice_id, practice_catalog),
        ),
    ]
    if show_done:
        action_row.append(
            InlineKeyboardButton(
                "✅ Я сделал!",
                callback_data=format_practice_callback("practice_done", practice_id, practice_catalog),
            ),
        )
    rows = [action_row]
    if total > 1:
        nav = []
        if index > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"fav_nav:{index - 1}"))
        nav.append(InlineKeyboardButton(f"{index + 1} / {total}", callback_data="fav_noop"))
        if index < total - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"fav_nav:{index + 1}"))
        rows.append(nav)
    return InlineKeyboardMarkup(rows)


def get_main_reply_keyboard():
    """Reply-клавиатура режима Daily и Challenge: время, советы, пауза, доп. практики."""
    keyboard = [
        [KeyboardButton("Изменить время"), KeyboardButton("Советы")],
        [KeyboardButton("Пауза"), KeyboardButton("Еще практики")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_by_mood_reply_keyboard():
    """Reply-клавиатура режима By mood: фильтры по запросу."""
    buttons = [KeyboardButton(spec.label) for spec in get_active_quick_filters()]
    keyboard = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
    )
