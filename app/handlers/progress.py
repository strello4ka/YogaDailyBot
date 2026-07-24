"""Обработчики кнопки «Мой прогресс» и сброса прогресса."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.challenge.cohort import CHALLENGE_DURATION
from data.db import (
    get_challenge_completed_in_last_n_days,
    get_completed_count,
    get_similar_result_percent,
    get_streak_days,
    get_user_bot_mode,
    reset_user_progress,
)


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
    return f"Прогресс в челлендже: *{completed}/{CHALLENGE_DURATION}* дней"


def format_progress_stats(n: int, streak: int, challenge_line: str = "") -> str:
    """Строки прогресса: всего выполнено, серия (если > 0), опционально челлендж."""
    streak_line = format_streak_line(streak)
    lines = [f"Выполнено всего практик: *{n}*"]
    if streak_line:
        lines.append(streak_line)
    if challenge_line:
        lines.append(challenge_line)
    return "\n".join(lines)


def format_similar_result_line(n: int, similar_percent) -> str:
    """Текст про долю пользователей с таким же результатом (по числу выполненных)."""
    if n == 0:
        return ""
    if n < 3 or similar_percent is None:
        return "\n\n\\*уже считаю сколько пользователей с таким же результатом\\*"
    if similar_percent < 1:
        return "\n\n*Менее 1%* пользователей YogaDailyBot имеют такой же результат..Ты неповторим!"
    return f"\n\nТакой же результат сейчас у *{round(similar_percent)}%* пользователей YogaDailyBot"


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


def _similar_result_line(user_id: int) -> str:
    """Текст про долю пользователей с таким же результатом."""
    n = get_completed_count(user_id)
    similar_percent = get_similar_result_percent(user_id, bucket_size=5, min_completed=3)
    return format_similar_result_line(n, similar_percent)


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
    text += _similar_result_line(user_id)
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
