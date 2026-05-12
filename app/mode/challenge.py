"""Модуль челленджа: команды /challenge и /challenge_off, выбор практики для ежедневной рассылки.

Функции БД (get_user_challenge_start_id, set_user_challenge, clear_user_challenge,
get_yoga_practice_by_id, get_yoga_practice_by_challenge_order и т.д.) остаются в data.postgres_db.
"""

import logging
import re
from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from app.keyboards import (
    MODE_CHOICE_INTRO_MARKDOWN,
    get_main_reply_keyboard,
    get_mode_choice_keyboard,
    get_welcome_keyboard,
)

from data.db import (
    get_yoga_practice_by_id,
    clear_user_challenge,
    complete_user_challenge_setup,
    get_user_challenge_start_id,
    get_yoga_practice_by_challenge_order,
    start_user_challenge_setup,
)

logger = logging.getLogger(__name__)

PENDING_CHALLENGE_PRACTICE_KEY = "pending_challenge_practice_id"
CHALLENGE_TIME_FLOW_KEY = "waiting_for_challenge_time"

CHALLENGE_WELCOME_TEXT = (
    "Ура, ты в *челлендже* 🧡\n\n"
    "Давай *выберем время*, в которое ты хочешь получать ежедневные практики, начиная с завтрашнего дня"
)

CHALLENGE_TIME_INPUT_TEXT = (
    "*Введи время в формате ЧЧ.ММ (например, 09.30)*\n\n"
    "PS. Время учитывается по МСК"
)


async def begin_challenge_time_selection_flow(
    update: Update, context: ContextTypes.DEFAULT_TYPE, practice_id: int
) -> None:
    """Единый вход в челлендж: приветствие + inline «Выбрать время»; id практики храним до ввода времени."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not start_user_challenge_setup(
        user.id,
        chat_id,
        practice_id,
        user_name=user.first_name,
        user_nickname=user.username,
    ):
        await update.message.reply_text(
            "Сначала нажми /start, а потом запусти челлендж ещё раз."
        )
        return
    context.user_data[PENDING_CHALLENGE_PRACTICE_KEY] = practice_id
    time_choice_message = await update.message.reply_text(
        CHALLENGE_WELCOME_TEXT,
        reply_markup=get_welcome_keyboard(),
        parse_mode="Markdown",
    )
    context.user_data["daily_time_choice_chat_id"] = chat_id
    context.user_data["daily_time_choice_message_id"] = time_choice_message.message_id


async def handle_challenge_time_choice_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Кнопка «Выбрать время» внутри сценария челленджа."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    from app.onboarding import remove_callback_keyboard, schedule_reminders

    await remove_callback_keyboard(query)
    context.user_data.pop("daily_time_choice_chat_id", None)
    context.user_data.pop("daily_time_choice_message_id", None)
    context.user_data.pop("waiting_for_practice_suggestion", None)
    context.user_data.pop("is_time_change", None)
    context.user_data["waiting_for_time"] = True
    context.user_data[CHALLENGE_TIME_FLOW_KEY] = True

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await context.bot.send_message(
        chat_id=chat_id,
        text=CHALLENGE_TIME_INPUT_TEXT,
        parse_mode="Markdown",
    )
    if hasattr(context, "job_queue") and context.job_queue is not None:
        await schedule_reminders(context, chat_id, user_id)


def _validate_time_format(time_str: str) -> tuple[bool, str]:
    time_str = time_str.strip().replace(".", ":")
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if not match:
        return False, "Хм, такой формат времени я не понимаю."
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour < 0 or hour > 23:
        return False, "Ой, часы должны быть от 0 до 23."
    if minute < 0 or minute > 59:
        return False, "Ой, минуты должны быть от 00 до 59."
    return True, f"{hour:02d}:{minute:02d}"


async def handle_challenge_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ввод времени для челленджа: сохраняем время и активируем bot_mode='challenge'."""
    is_valid, result = _validate_time_format(update.message.text)
    if not is_valid:
        await update.message.reply_text(
            f"🚨 {result}\n\n"
            "Попробуй еще раз в формате ЧЧ.ММ"
        )
        return

    selected_time = result
    user = update.effective_user
    chat_id = update.effective_chat.id
    context.user_data.pop("waiting_for_time", None)
    context.user_data.pop(CHALLENGE_TIME_FLOW_KEY, None)

    from app.onboarding import cancel_reminders

    await cancel_reminders(context, user.id)
    if not complete_user_challenge_setup(
        user.id,
        chat_id,
        selected_time,
        user_name=user.first_name,
        user_nickname=user.username,
    ):
        await update.message.reply_text(
            "Время сохранилось не полностью: не получилось запустить челлендж. "
            "Попробуй ещё раз команду /challenge."
        )
        return

    context.user_data.pop(PENDING_CHALLENGE_PRACTICE_KEY, None)
    await update.message.reply_text(
        (
            "Готово ✔️\n\n"
            f"Твоё время *{selected_time}*.\n"
            "Длительность челленджа — 28 дней.\n"
            f"Завтра в *{selected_time}* жди свою первую практику.\n\n"
            "Уже жду тебя 🧡"
        ),
        parse_mode="Markdown",
    )
    await update.message.reply_text(
        (
            "Внизу у тебя появились кнопки:\n\n"
            "🕓 Изменить время — жми, чтобы изменить время рассылки\n"
            "💡 Советы — жми обязательно\n"
            "🪫 Пауза — приостановить или возобновить ежедневную рассылку\n\n"
            "Также есть *Меню*, где можно посмотреть свой прогресс, задонатить и найти другую полезную инфу"
        ),
        reply_markup=get_main_reply_keyboard(),
    )


def get_practice_for_daily_send(user_id: int, weekday: int, challenge_day: int):
    """Возвращает практику для рассылки, если пользователь в режиме челленджа; иначе None.

    Используется планировщиком: если вернул (practice, True), отправлять эту практику;
    если (None, False) — планировщик берёт практику по дню недели.

    Returns:
        tuple: (practice или None, is_challenge: bool)
    """
    start_id = get_user_challenge_start_id(user_id)
    if start_id is None:
        return (None, False)
    practice = get_yoga_practice_by_challenge_order(start_id, challenge_day)
    return (practice, True)


async def challenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда челленджа: /challenge <id>."""
    user_id = update.effective_user.id
    if not context.args or len(context.args) != 1:
        return
    try:
        practice_id = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("Нужно указать число — id практики. Пример: /challenge 54")
        return
    await _start_challenge(update, context, user_id, practice_id)


async def challenge_compact_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда челленджа в формате /challenge<id>, например /challenge61."""
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    match = re.match(r"^/challenge(?:@[\w_]+)?(\d+)$", text)
    if not match:
        return
    practice_id = int(match.group(1))
    await _start_challenge(update, context, user_id, practice_id)


async def _start_challenge(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, practice_id: int
):
    """Запуск челленджа: один сценарий — приветствие и выбор времени, затем bot_mode='challenge'."""
    if practice_id < 1:
        await update.message.reply_text("Id практики должен быть положительным числом.")
        return
    practice = get_yoga_practice_by_id(practice_id)
    if not practice:
        await update.message.reply_text(f"Упс, что-то не то. Попробуй другую команду")
        return
    await begin_challenge_time_selection_flow(update, context, practice_id)
    logger.info(
        "Пользователь %s открыл экран выбора времени для челленджа (practice_id=%s)",
        user_id,
        practice_id,
    )


async def challenge_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из режима челленджа: переводим пользователя в pending и показываем выбор режима."""
    user_id = update.effective_user.id
    context.user_data.pop(PENDING_CHALLENGE_PRACTICE_KEY, None)
    context.user_data.pop(CHALLENGE_TIME_FLOW_KEY, None)
    context.user_data.pop("waiting_for_time", None)
    clear_user_challenge(user_id)
    await update.message.reply_text(
        "Режим челленджа завершен ✔️\n"
        "Какой бы ни был твой результат, ты супер!\n"
        "Продолжай использовать бот, чтобы сохранить привычку. Твой прогресс будет сохранен.\n\n"
        "Выбери, как дальше работать с ботом:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text(
        MODE_CHOICE_INTRO_MARKDOWN,
        reply_markup=get_mode_choice_keyboard(),
        parse_mode="Markdown",
    )
    logger.info(f"Пользователь {user_id} выключил челлендж")
