"""Обработчики кнопки «Мой прогресс» и сброса прогресса."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.challenge.cohort import CHALLENGE_DURATION
from data.db import (
    get_better_than_completed_percent,
    get_challenge_completed_in_last_n_days,
    get_completed_count,
    get_streak_days,
    get_user_bot_mode,
    has_best_streak,
    reset_user_progress,
)

# Пороги «лучше, чем у X%» по числу выполненных практик
_MIN_SHOW_BETTER_THAN = 50
_TOP_10_THRESHOLD = 90
_TOP_5_THRESHOLD = 95
_TOP_1_THRESHOLD = 99
_MIN_COMPLETED_FOR_COMPARE = 3
_MIN_STREAK_FOR_BEST = 7

BEST_STREAK_LINE = "\n\nУ тебя сейчас ЛУЧШАЯ непрерывная серия в YogaDailyBot🔥"


def format_streak_line(streak: int) -> str:
    """Строка про непрерывную серию дней; пустая, если серии нет."""
    if streak <= 0:
        return ""
    return f"Непрерывная серия дней: *{streak}*"


def format_challenge_progress_line(user_id: int) -> str:
    """Строка прогресса челленджа N/28; пустая, если режим не challenge."""
    if get_user_bot_mode(user_id) != "challenge":
        return ""
    completed = get_challenge_completed_in_last_n_days(user_id, CHALLENGE_DURATION)
    return f"Прогресс в челлендже: *{completed}/{CHALLENGE_DURATION}*"


def format_progress_stats(n: int, streak: int, challenge_line: str = "") -> str:
    """Строки прогресса: всего выполнено, серия (если > 0), опционально челлендж."""
    streak_line = format_streak_line(streak)
    lines = [f"Выполнено всего практик: *{n}*"]
    if streak_line:
        lines.append(streak_line)
    if challenge_line:
        lines.append(challenge_line)
    return "\n".join(lines)


def format_completed_rank_line(better_than_percent) -> str:
    """Фраза сравнения по числу практик; пустая, если ниже 50% или нет данных."""
    if better_than_percent is None:
        return ""
    x = round(better_than_percent)
    if x < _MIN_SHOW_BETTER_THAN:
        return ""
    if x >= _TOP_1_THRESHOLD:
        return (
            "\n\nТы главный йог YogaDailyBot! "
            "Только *1%* пользователей выполнили так много практик!!!!"
        )
    if x >= _TOP_5_THRESHOLD:
        return "\n\nТы среди лучших: такой результат только у *5%* пользователей!"
    if x >= _TOP_10_THRESHOLD:
        return (
            "\n\nТы входишь в топ *10%* пользователей YogaDailyBot "
            "по количеству выполненных практик!"
        )
    return f"\n\nТы выполнил больше практик, чем *{x}%* пользователей YogaDailyBot!"


def format_social_proof_line(user_id: int) -> str:
    """Соц. фраза: лучшая серия важнее сравнения по числу практик."""
    if has_best_streak(user_id, min_streak=_MIN_STREAK_FOR_BEST):
        return BEST_STREAK_LINE
    n = get_completed_count(user_id)
    if n < _MIN_COMPLETED_FOR_COMPARE:
        return ""
    better_than = get_better_than_completed_percent(
        user_id, min_completed=_MIN_COMPLETED_FOR_COMPARE
    )
    return format_completed_rank_line(better_than)


# Совместимость со старым именем в done.py
def format_similar_result_line(n: int, similar_percent) -> str:
    """Устарело: используйте format_social_proof_line / format_completed_rank_line."""
    return format_completed_rank_line(similar_percent)


def _progress_text(user_id: int) -> str:
    """Формирует текст прогресса: всего выполнено + серия дней (+ челлендж)."""
    n = get_completed_count(user_id)
    if n == 0:
        challenge_line = format_challenge_progress_line(user_id)
        if challenge_line:
            return f"Ты еще не выполнил ни одной практики, все самое прекрасное впереди✨\n\n{challenge_line}"
        return "Ты еще не выполнил ни одной практики, все самое прекрасное впереди✨"
    streak = get_streak_days(user_id)
    return format_progress_stats(n, streak, format_challenge_progress_line(user_id))


def _progress_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой «Сбросить прогресс»."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Сбросить прогресс", callback_data="progress_reset")]
    ])


def _confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения сброса."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Да, сбросить", callback_data="progress_reset_yes")],
        [InlineKeyboardButton("Нет", callback_data="progress_reset_no")]
    ])


async def handle_progress_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки «Мой прогресс»: показывает прогресс и кнопку сброса."""
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        return
    msg = update.effective_message
    if not msg:
        return
    text = _progress_text(user_id)
    text += format_social_proof_line(user_id)
    # Во время челленджа сброс недоступен — иначе сотрётся зачёт N/28
    show_reset = get_completed_count(user_id) > 0 and get_user_bot_mode(user_id) != "challenge"
    reply_markup = _progress_keyboard() if show_reset else None
    await msg.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_progress_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """По нажатию «Сбросить прогресс» — показать подтверждение."""
    query = update.callback_query
    if not query:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if user_id and get_user_bot_mode(user_id) == "challenge":
        await query.answer()
        await query.edit_message_text(
            "Во время челленджа сброс прогресса недоступен — чтобы не сбросить зачёт дней потока"
        )
        return
    await query.answer()
    await query.edit_message_text(
        "Точно хочешь сбросить? Практики будут приходить как раньше, просто цифры начнутся заново.",
        reply_markup=_confirm_keyboard()
    )


async def handle_progress_reset_yes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """По нажатию «Да, сбросить» — сброс прогресса и ответ."""
    query = update.callback_query
    if not query:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await query.answer("Ошибка.")
        return
    if get_user_bot_mode(user_id) == "challenge":
        await query.answer()
        await query.edit_message_text(
            "Во время челленджа сброс прогресса недоступен — чтобы не сбросить зачёт дней потока"
        )
        return
    reset_user_progress(user_id)
    await query.answer()
    await query.edit_message_text("Готово, прогресс сброшен. Следующая практика придёт по расписанию как обычно. Новый старт - новый настрой!")


async def handle_progress_reset_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """По нажатию «Отмена» — убрать подтверждение."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await query.edit_message_text("Оставляем как есть. Продолжай в том же духе!")
