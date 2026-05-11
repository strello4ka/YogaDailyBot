"""Сценарий «Сам решу»: время → интенсивность → случайная практика."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from data.db import pick_random_by_mood_practice

from .send_utils import deliver_by_mood_practice

TIME_LABELS = ["до 10", "10 - 15", "15 - 20", "20 - 25", "больше 25", "любое"]
INTENSITY_LABELS = ["низкая", "средняя", "высокая", "любая"]

TIME_TO_KEY = {
    "до 10": "t10",
    "10 - 15": "t10_15",
    "15 - 20": "t15_20",
    "20 - 25": "t20_25",
    "больше 25": "t25p",
    "любое": "tany",
}
KEY_TO_TIME = {value: key for key, value in TIME_TO_KEY.items()}

INTENSITY_TO_KEY = {
    "низкая": "ilow",
    "средняя": "imed",
    "высокая": "ihigh",
    "любая": "iany",
}
KEY_TO_INTENSITY = {value: key for key, value in INTENSITY_TO_KEY.items()}


def time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("до 10", callback_data="self_time:t10"),
                InlineKeyboardButton("10 - 15", callback_data="self_time:t10_15"),
            ],
            [
                InlineKeyboardButton("15 - 20", callback_data="self_time:t15_20"),
                InlineKeyboardButton("20 - 25", callback_data="self_time:t20_25"),
            ],
            [
                InlineKeyboardButton("больше 25", callback_data="self_time:t25p"),
                InlineKeyboardButton("любое", callback_data="self_time:tany"),
            ],
        ]
    )


def intensity_keyboard(time_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("низкая", callback_data=f"self_intensity:{time_key}:ilow"),
                InlineKeyboardButton("средняя", callback_data=f"self_intensity:{time_key}:imed"),
            ],
            [
                InlineKeyboardButton("высокая", callback_data=f"self_intensity:{time_key}:ihigh"),
                InlineKeyboardButton("любая", callback_data=f"self_intensity:{time_key}:iany"),
            ],
        ]
    )


def _sql_for_time_choice(label: str) -> tuple[str, tuple]:
    if label == "до 10":
        return " AND yp.time_practices <= 10 AND yp.time_practices > 0 ", ()
    if label == "10 - 15":
        return " AND yp.time_practices > 10 AND yp.time_practices <= 15 ", ()
    if label == "15 - 20":
        return " AND yp.time_practices > 15 AND yp.time_practices <= 20 ", ()
    if label == "20 - 25":
        return " AND yp.time_practices > 20 AND yp.time_practices <= 25 ", ()
    if label == "больше 25":
        return " AND yp.time_practices > 25 ", ()
    return "", ()


def _sql_for_intensity_choice(label: str) -> tuple[str, tuple]:
    if label == "низкая":
        return (
            " AND LOWER(TRIM(COALESCE(yp.intensity, ''))) IN ('низкая', 'низкий') ",
            (),
        )
    if label == "средняя":
        return " AND LOWER(TRIM(COALESCE(yp.intensity, ''))) IN ('средняя', 'средний') ", ()
    if label == "высокая":
        return " AND LOWER(TRIM(COALESCE(yp.intensity, ''))) IN ('высокая', 'высокий') ", ()
    return "", ()


async def start_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Настрой свою практику *сам*:\nсначала выбери время (в минутах)👇",
        reply_markup=time_keyboard(),
    )


async def handle_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    time_key = (query.data or "").split(":", 1)[1]
    if time_key not in KEY_TO_TIME:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «Сам решу» ещё раз.")
        return

    await query.edit_message_text(
        "Время выбрано ✔️\nТеперь выбери интенсивность 👇",
        reply_markup=intensity_keyboard(time_key),
    )


async def handle_intensity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    try:
        _prefix, time_key, intensity_key = (query.data or "").split(":", 2)
    except ValueError:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «Сам решу» ещё раз.")
        return

    time_label = KEY_TO_TIME.get(time_key)
    intensity_label = KEY_TO_INTENSITY.get(intensity_key)
    if not time_label or not intensity_label:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «Сам решу» ещё раз.")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    filter_key = f"self_{time_key}_{intensity_key}"
    wh_time, par_time = _sql_for_time_choice(time_label)
    wh_int, par_int = _sql_for_intensity_choice(intensity_label)
    row = pick_random_by_mood_practice(user.id, filter_key, wh_time + wh_int, par_time + par_int)
    if not row:
        await query.message.reply_text(
            "Не нашлось практики с такими параметрами. Попробуй смягчить фильтры (например, «любое» и «любая» интенсивность)."
        )
        return

    ok = await deliver_by_mood_practice(context, chat.id, user.id, filter_key, row)
    if not ok:
        await query.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")
