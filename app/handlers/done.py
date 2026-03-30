"""Обработчик кнопки «✔️Я сделал!» под сообщением с практикой."""

from telegram import Update
from telegram.ext import ContextTypes

from data.db import (
    mark_practice_completed_today,
    get_completed_count,
    get_user_days,
    get_similar_result_percent,
    get_user_challenge_start_id,
)


ACHIEVEMENT_MESSAGES = {
    1: "Ура! Начало положено, заглядывай еще 🫂",
    3: "Ого, ты набираешь обороты 🧡",
    5: "Давай дневник, ставлю 5️⃣",
    10: "Первая ДЕСЯТОЧКА! Очень горжусь твоей дисциплиной 🫂",
    15: "Легенда коврика, официально ✨",
    20: "20 ДНЕЙ С ПРАКТИКОЙ!Ты настоящий йога-двигатель 🔋",
    25: "Ритм держишь как профи 🧡 ",
    30: "30 — это уже уровень мастера привычек 🧘‍♂️",
    40: "40 ДНЕЙ С ПРАКТИКОЙ!Такой темп пугает и восхищает одновременно 🌀",
    50: "ПОЛСОТНИ — уровень МАШИНА 🦾",
    60: "Ты уже сверхчеловек на коврике...",
    70: "Кажется, тебя уже не остановить 🧘‍♂️",
    80: "До сотни рукой подать — добивай красиво 🪄",
    90: "90! До сотни один вдох и выдох ✨",
    100: "100!!! Всё, теперь ты легально гуру йоги 🧘‍♂️🧘‍♂️🧘‍♂️",
    150: "Ты не тренируешься — ты доминируешь 🔋",
    200: "200!!!! Спокойно… ты вообще человек?",
    250: "Ты пример того, как работает система и характер 💙",
    300: "300!!! Ты просто монстр 💪",
    365: "365 дней в году и столько раз ты занимался йогой вместе мной, наши отношения переходят на новый уровень 🫂",
}


def _similar_result_line(m: int, similar_percent) -> str:
    """Текст про долю пользователей с таким же результатом."""
    if m < 5 or similar_percent is None:
        return "\n\\*уже считаю сколько пользователей с таким же результатом\\*"
    if similar_percent < 1:
        return "\nМенее 1% пользователей YogaDailyBot имеют такой же результат..Ты неповторим!"
    return f"\nТакой же результат сейчас у {round(similar_percent)}% пользователей YogaDailyBot"


def _done_text(n: int, m: int, is_challenge: bool, similar_line: str) -> str:
    """Текст после отметки практики с ачивками на заданных порогах."""
    title = ACHIEVEMENT_MESSAGES.get(n, "Ты супер🧡")
    if is_challenge:
        return f"{title}\n\nВыполнено практик: *{n}*"
    return f"{title}\n\nВыполнено практик: *{n} из {m}*{similar_line}"


async def handle_practice_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия «✔️Я сделал!»: отмечает последнюю практику выполненной и показывает прогресс."""
    query = update.callback_query
    if not query:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id:
        await query.answer("Ошибка: пользователь не определён.")
        return

    ok = mark_practice_completed_today(user_id)
    await query.answer()  # убираем «часики» на кнопке, без всплывающего текста
    if ok:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        n = get_completed_count(user_id)
        m = get_user_days(user_id)
        is_challenge = get_user_challenge_start_id(user_id) is not None
        similar_percent = None if is_challenge else get_similar_result_percent(
            user_id, bucket_size=5, min_received=5
        )
        similar_line = "" if is_challenge else _similar_result_line(m, similar_percent)
        text = _done_text(n, m, is_challenge, similar_line)
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            parse_mode='Markdown',
        )
