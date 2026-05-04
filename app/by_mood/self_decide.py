"""Сценарий «сам решу»: время → интенсивность → случайная практика."""

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.keyboards import get_by_mood_reply_keyboard
from data.db import pick_random_by_mood_practice

from .send_utils import deliver_by_mood_practice

TIME_LABELS = ["до 15 мин", "до 30 мин", "до 45 мин", "до 60 мин", "больше 60 мин", "любое время"]
INTENSITY_LABELS = ["низкая", "средняя", "высокая", "любая"]

TIME_TO_KEY = {
    "до 15 мин": "t15",
    "до 30 мин": "t30",
    "до 45 мин": "t45",
    "до 60 мин": "t60",
    "больше 60 мин": "t60p",
    "любое время": "tany",
}

INTENSITY_TO_KEY = {
    "низкая": "ilow",
    "средняя": "imed",
    "высокая": "ihigh",
    "любая": "iany",
}


def time_keyboard() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(l)] for l in TIME_LABELS]
    rows.append([KeyboardButton("Отмена")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def intensity_keyboard() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(l)] for l in INTENSITY_LABELS]
    rows.append([KeyboardButton("Отмена")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def _sql_for_time_choice(label: str) -> tuple[str, tuple]:
    if label == "до 15 мин":
        return " AND yp.time_practices <= 15 AND yp.time_practices > 0 ", ()
    if label == "до 30 мин":
        return " AND yp.time_practices <= 30 AND yp.time_practices > 0 ", ()
    if label == "до 45 мин":
        return " AND yp.time_practices <= 45 AND yp.time_practices > 0 ", ()
    if label == "до 60 мин":
        return " AND yp.time_practices <= 60 AND yp.time_practices > 0 ", ()
    if label == "больше 60 мин":
        return " AND yp.time_practices > 60 ", ()
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


def clear_self_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("by_mood_self_step", None)
    context.user_data.pop("by_mood_self_time", None)


async def start_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["by_mood_self_step"] = "time"
    context.user_data.pop("by_mood_self_time", None)
    await update.message.reply_text(
        "Ок, соберём практику под тебя.\n\n*Шаг 1.* Выбери длительность (примерное время видео):",
        parse_mode="Markdown",
        reply_markup=time_keyboard(),
    )


async def handle_text_in_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает ответы сценария «сам решу». Возвращает True, если сообщение обработано."""
    step = context.user_data.get("by_mood_self_step")
    if not step:
        return False

    text = (update.message.text or "").strip()
    if text == "Отмена":
        clear_self_state(context)
        await update.message.reply_text(
            "Ок, отменила подбор. Выбирай готовый фильтр с клавиатуры.",
            reply_markup=get_by_mood_reply_keyboard(),
        )
        return True

    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False

    if step == "time":
        if text not in TIME_LABELS:
            await update.message.reply_text("Выбери один из вариантов на кнопках ниже или «Отмена».")
            return True
        context.user_data["by_mood_self_time"] = text
        context.user_data["by_mood_self_step"] = "intensity"
        await update.message.reply_text(
            "*Шаг 2.* Какая интенсивность?",
            parse_mode="Markdown",
            reply_markup=intensity_keyboard(),
        )
        return True

    if step == "intensity":
        if text not in INTENSITY_LABELS:
            await update.message.reply_text("Выбери интенсивность на кнопках или «Отмена».")
            return True
        time_label = context.user_data.get("by_mood_self_time")
        if not time_label or time_label not in TIME_TO_KEY:
            clear_self_state(context)
            await update.message.reply_text("Что-то пошло не так. Нажми «сам решу» ещё раз.")
            return True

        tkey = TIME_TO_KEY[time_label]
        ikey = INTENSITY_TO_KEY[text]
        filter_key = f"self_{tkey}_{ikey}"

        wh_time, par_time = _sql_for_time_choice(time_label)
        wh_int, par_int = _sql_for_intensity_choice(text)
        extra_where = wh_time + wh_int
        extra_params = par_time + par_int

        clear_self_state(context)

        row = pick_random_by_mood_practice(user.id, filter_key, extra_where, extra_params)
        if not row:
            await update.message.reply_text(
                "Не нашлось практики с такими параметрами. Попробуй смягчить фильтры (например, «любое время» и «любая» интенсивность).",
                reply_markup=get_by_mood_reply_keyboard(),
            )
            return True

        await update.message.reply_text(
            "Лови подходящую практику 🧡",
            reply_markup=get_by_mood_reply_keyboard(),
        )
        ok = await deliver_by_mood_practice(context, chat.id, user.id, filter_key, row)
        if not ok:
            await update.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")
        return True

    return False
