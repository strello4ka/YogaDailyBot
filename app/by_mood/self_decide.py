"""Сценарий «САМ решу»: время → сложность → случайная практика."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from data.db import pick_random_combined_mood_pool, remove_extra_practices_inline_message

from .send_utils import deliver_by_mood_practice

TIME_LABELS = ["до 10", "10 - 15", "15 - 20", "20 - 30", "30 - 45", "45 - 60+", "любое"]
DIFFICULTY_LABELS = ["низкая", "средняя", "высокая", "любая"]

TIME_TO_KEY = {
    "до 10": "t10",
    "10 - 15": "t10_15",
    "15 - 20": "t15_20",
    "20 - 30": "t20_30",
    "30 - 45": "t30_45",
    "45 - 60+": "t45_60p",
    "любое": "tany",
}
KEY_TO_TIME = {value: key for key, value in TIME_TO_KEY.items()}

DIFFICULTY_TO_KEY = {
    "низкая": "ilow",
    "средняя": "imed",
    "высокая": "ihigh",
    "любая": "iany",
}
KEY_TO_DIFFICULTY = {value: key for key, value in DIFFICULTY_TO_KEY.items()}


def time_keyboard(*, callback_prefix: str = "self_time") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("до 10", callback_data=f"{callback_prefix}:t10"),
                InlineKeyboardButton("10 - 15", callback_data=f"{callback_prefix}:t10_15"),
            ],
            [
                InlineKeyboardButton("15 - 20", callback_data=f"{callback_prefix}:t15_20"),
                InlineKeyboardButton("20 - 30", callback_data=f"{callback_prefix}:t20_30"),
            ],
            [
                InlineKeyboardButton("30 - 45", callback_data=f"{callback_prefix}:t30_45"),
                InlineKeyboardButton("45 - 60+", callback_data=f"{callback_prefix}:t45_60p"),
            ],
            [
                InlineKeyboardButton("любое", callback_data=f"{callback_prefix}:tany"),
            ],
        ]
    )


def difficulty_keyboard(time_key: str, *, callback_prefix: str = "self_difficulty") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("низкая", callback_data=f"{callback_prefix}:{time_key}:ilow"),
                InlineKeyboardButton("средняя", callback_data=f"{callback_prefix}:{time_key}:imed"),
            ],
            [
                InlineKeyboardButton("высокая", callback_data=f"{callback_prefix}:{time_key}:ihigh"),
                InlineKeyboardButton("любая", callback_data=f"{callback_prefix}:{time_key}:iany"),
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
    if label == "20 - 30":
        return " AND yp.time_practices > 20 AND yp.time_practices <= 30 ", ()
    if label == "30 - 45":
        return " AND yp.time_practices > 30 AND yp.time_practices <= 45 ", ()
    if label == "45 - 60+":
        return " AND yp.time_practices > 45 ", ()
    return "", ()


def _sql_for_difficulty_choice(label: str) -> tuple[str, tuple]:
    if label == "низкая":
        return (
            " AND LOWER(TRIM(COALESCE(yp.difficulty, ''))) IN ('низкая', 'низкий') ",
            (),
        )
    if label == "средняя":
        return " AND LOWER(TRIM(COALESCE(yp.difficulty, ''))) IN ('средняя', 'средний') ", ()
    if label == "высокая":
        return " AND LOWER(TRIM(COALESCE(yp.difficulty, ''))) IN ('высокая', 'высокий') ", ()
    return "", ()


async def start_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Настрой свою практику *сам*:\nсначала выбери время (в минутах)👇",
        parse_mode="Markdown",
        reply_markup=time_keyboard(),
    )


async def handle_time_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    time_callback_prefix: str = "self_time",
    difficulty_callback_prefix: str = "self_difficulty",
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    pfx = f"{time_callback_prefix}:"
    if not data.startswith(pfx):
        return
    time_key = data[len(pfx) :]
    if time_key not in KEY_TO_TIME:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «САМ решу» ещё раз.")
        return

    await query.edit_message_text(
        "Время выбрано ✔️\nТеперь выбери сложность 👇",
        reply_markup=difficulty_keyboard(time_key, callback_prefix=difficulty_callback_prefix),
    )


async def handle_difficulty_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    difficulty_callback_prefix: str = "self_difficulty",
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    pfx = f"{difficulty_callback_prefix}:"
    if not data.startswith(pfx):
        return
    rest = data[len(pfx) :]
    try:
        time_key, difficulty_key = rest.split(":", 1)
    except ValueError:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «САМ решу» ещё раз.")
        return

    time_label = KEY_TO_TIME.get(time_key)
    difficulty_label = KEY_TO_DIFFICULTY.get(difficulty_key)
    if not time_label or not difficulty_label:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «САМ решу» ещё раз.")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    remove_extra_practices_inline_message(user.id, chat.id, query.message.message_id)

    filter_key = f"self_{time_key}_{difficulty_key}"
    wh_time, par_time = _sql_for_time_choice(time_label)
    wh_int, par_int = _sql_for_difficulty_choice(difficulty_label)
    row = pick_random_combined_mood_pool(user.id, filter_key, wh_time + wh_int, par_time + par_int)
    if not row:
        await query.message.reply_text(
            "Не нашлось практики с такими параметрами. Попробуй смягчить фильтры (например, «любое» время или «любая» сложность)."
        )
        return

    ok = await deliver_by_mood_practice(context, chat.id, user.id, filter_key, row)
    if not ok:
        await query.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")
