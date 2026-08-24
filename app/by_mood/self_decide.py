"""Сценарий «САМ решу»: время → акцент → сложность → практика."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from data.db import (
    get_available_combined_difficulties,
    get_available_combined_tegs,
    pick_random_combined_mood_pool,
    remove_extra_practices_inline_message,
)

from .send_utils import deliver_by_mood_practice

TIME_LABELS = ["до 10", "10 - 15", "15 - 20", "20 - 30", "30 - 45", "45 - 60+", "любое"]
DIFFICULTY_LABELS = ["низкая", "средняя", "высокая", "любая"]
TEG_LABELS = [
    "Сильное тело",
    "Сильные ноги",
    "Расслабление",
    "Зарядка",
    "Здоровая спина",
    "Кор и пресс",
    "Балансы на руках",
    "ТБС и шпагаты",
    "Всё тело",
]
ANY_TEG_LABEL = "любой"

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

TEG_TO_KEY = {
    "Сильное тело": "strong_body",
    "Сильные ноги": "strong_legs",
    "Расслабление": "relax",
    "Зарядка": "charge",
    "Здоровая спина": "back",
    "Кор и пресс": "core",
    "Балансы на руках": "arm_balance",
    "ТБС и шпагаты": "hips",
    "Всё тело": "whole_body",
    ANY_TEG_LABEL: "any",
}
KEY_TO_TEG = {value: key for key, value in TEG_TO_KEY.items()}

DIFFICULTY_TO_KEY = {
    "низкая": "ilow",
    "средняя": "imed",
    "высокая": "ihigh",
    "любая": "iany",
}
KEY_TO_DIFFICULTY = {value: key for key, value in DIFFICULTY_TO_KEY.items()}

DIFFICULTY_DB_VALUES = {
    "низкая": {"низкая", "низкий"},
    "средняя": {"средняя", "средний"},
    "высокая": {"высокая", "высокий"},
}


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


def _button_rows(buttons: list[InlineKeyboardButton]) -> list[list[InlineKeyboardButton]]:
    return [buttons[index : index + 2] for index in range(0, len(buttons), 2)]


def teg_keyboard(
    time_key: str,
    available_tegs: set[str],
    *,
    callback_prefix: str = "self_teg",
) -> InlineKeyboardMarkup:
    labels = [label for label in TEG_LABELS if label in available_tegs]
    labels.append(ANY_TEG_LABEL)
    buttons = [
        InlineKeyboardButton(
            label,
            callback_data=f"{callback_prefix}:{time_key}:{TEG_TO_KEY[label]}",
        )
        for label in labels
    ]
    return InlineKeyboardMarkup(_button_rows(buttons))


def difficulty_keyboard(
    time_key: str,
    teg_key: str,
    available_difficulties: set[str],
    *,
    callback_prefix: str = "self_difficulty",
) -> InlineKeyboardMarkup:
    normalized = {value.strip().lower() for value in available_difficulties}
    labels = [
        label
        for label in DIFFICULTY_LABELS[:-1]
        if normalized & DIFFICULTY_DB_VALUES[label]
    ]
    labels.append("любая")
    buttons = [
        InlineKeyboardButton(
            label,
            callback_data=(
                f"{callback_prefix}:{time_key}:{teg_key}:{DIFFICULTY_TO_KEY[label]}"
            ),
        )
        for label in labels
    ]
    return InlineKeyboardMarkup(_button_rows(buttons))


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


def _sql_for_teg_choice(label: str) -> tuple[str, tuple]:
    if label == ANY_TEG_LABEL:
        return "", ()
    return (
        " AND %s = ANY(COALESCE(yp.teg, ARRAY[]::TEXT[])) ",
        (label,),
    )


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
    teg_callback_prefix: str = "self_teg",
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
        "Время выбрано ✔️\nНа что сделать акцент? 👇",
        reply_markup=teg_keyboard(
            time_key,
            get_available_combined_tegs(*_sql_for_time_choice(KEY_TO_TIME[time_key])),
            callback_prefix=teg_callback_prefix,
        ),
    )


async def handle_teg_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    teg_callback_prefix: str = "self_teg",
    difficulty_callback_prefix: str = "self_difficulty",
) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    pfx = f"{teg_callback_prefix}:"
    if not data.startswith(pfx):
        return
    try:
        time_key, teg_key = data[len(pfx) :].split(":", 1)
    except ValueError:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «САМ решу» ещё раз.")
        return

    time_label = KEY_TO_TIME.get(time_key)
    teg_label = KEY_TO_TEG.get(teg_key)
    if not time_label or not teg_label:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «САМ решу» ещё раз.")
        return

    wh_time, par_time = _sql_for_time_choice(time_label)
    wh_teg, par_teg = _sql_for_teg_choice(teg_label)
    available = get_available_combined_difficulties(
        wh_time + wh_teg,
        par_time + par_teg,
    )
    await query.edit_message_text(
        "Акцент выбран ✔️\nТеперь выбери сложность 👇",
        reply_markup=difficulty_keyboard(
            time_key,
            teg_key,
            available,
            callback_prefix=difficulty_callback_prefix,
        ),
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
        time_key, teg_key, difficulty_key = rest.split(":", 2)
    except ValueError:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «САМ решу» ещё раз.")
        return

    time_label = KEY_TO_TIME.get(time_key)
    teg_label = KEY_TO_TEG.get(teg_key)
    difficulty_label = KEY_TO_DIFFICULTY.get(difficulty_key)
    if not time_label or not teg_label or not difficulty_label:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Что-то пошло не так. Нажми «САМ решу» ещё раз.")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    remove_extra_practices_inline_message(user.id, chat.id, query.message.message_id)

    filter_key = f"self_{time_key}_{teg_key}_{difficulty_key}"
    wh_time, par_time = _sql_for_time_choice(time_label)
    wh_teg, par_teg = _sql_for_teg_choice(teg_label)
    wh_int, par_int = _sql_for_difficulty_choice(difficulty_label)
    row = pick_random_combined_mood_pool(
        user.id,
        filter_key,
        wh_time + wh_teg + wh_int,
        par_time + par_teg + par_int,
    )
    if not row:
        await query.message.reply_text(
            "Не нашлось практики с такими параметрами. Попробуй смягчить фильтры (например, «любое» время или «любая» сложность)."
        )
        return

    ok = await deliver_by_mood_practice(context, chat.id, user.id, filter_key, row)
    if not ok:
        await query.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")
