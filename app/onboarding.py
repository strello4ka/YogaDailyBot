"""/start and onboarding handler for YogaDailyBot.
старт и онбординг.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CallbackContext
from data.db import activate_user_by_mood
from data.db import get_current_weekday, get_yoga_practice_by_weekday_order
from app.schedule.scheduler import format_practice_message

from .keyboards import (
    get_by_mood_reply_keyboard,
    get_choose_mode_keyboard,
    get_mode_choice_keyboard,
    get_start_onboarding_keyboard,
    get_welcome_keyboard,
)

MODE_CHOICE_INTRO_MARKDOWN = (
    "*Выбери режим работы бота:*\n\n"
    "🌀 Режим *Daily* — для тех, кто хочет мягко внедрить привычку заниматься *ежедневно* и не перегорать, ведь неделя содержит сбалансированный набор практик.\n"
    "*Выбираешь удобное время, и бот присылает видео в это время каждый день.*\n"
    "Ты не заметишь напряга, но станешь сильнее, выносливее и гибче!\n\n"
    "🌀 Режим *By mood* — для тех, кто хочет делать зарядки и разминки по состоянию в моменте, но без траты времени на поиск качественного контента.\n"
    "*Нажимаешь подходящую по настроению кнопку, и бот сразу подбирает практику под твой запрос: Ленивые дни, Мини, Практика дня и т.д.* Также можно самому настроить время и интенсивность.\n\n"
    "Оба режима помогают практиковать регулярно, просто разным способом:\n"
    "*Daily* — через привычку и стабильность\n"
    "*By mood* — через гибкость и свободу выбора.\n\n"
    "Выбирай то, что ближе тебе сейчас, и *жми кнопку* 👇 \n"
    "(изменить режим можно в любой момент в меню)"
)


def validate_time_format(time_str: str) -> tuple[bool, str]:
    """Проверяет формат времени и возвращает результат валидации.
    
    Args:
        time_str: Строка с временем (например, "09:30", "9:30", "9.30")
    
    Returns:
        tuple: (is_valid, error_message или formatted_time)
    """
    # Убираем пробелы
    time_str = time_str.strip()
    
    # Заменяем точку на двоеточие
    time_str = time_str.replace('.', ':')
    
    # Проверяем формат ЧЧ:ММ или Ч:ММ
    pattern = r'^(\d{1,2}):(\d{2})$'
    match = re.match(pattern, time_str)
    
    if not match:
        return False, "Хм, такой формат времени я не понимаю."
    
    hour = int(match.group(1))
    minute = int(match.group(2))
    
    # Проверяем диапазон часов и минут
    if hour < 0 or hour > 23:
        return False, "Ой, часы должны быть от 0 до 23."
    
    if minute < 0 or minute > 59:
        return False, "Ой, минуты должны быть от 00 до 59."
    
    # Форматируем время в стандартный вид ЧЧ:ММ
    formatted_time = f"{hour:02d}:{minute:02d}"
    return True, formatted_time


def _is_mode_choice_pending(user_id: int) -> bool:
    """True, если пользователь ещё не выбрал режим (застрял после /start)."""
    from data.db import get_user_bot_mode

    return get_user_bot_mode(user_id) == "pending"


def _is_daily_time_onboarding_pending(user_id: int) -> bool:
    """True, если Daily/Challenge выбран, но время ещё не сохранено."""
    from data.db import is_user_onboarding_required

    return is_user_onboarding_required(user_id)


# --- Тексты напоминаний (Markdown) ---

MODE_REMINDER_AFTER_START_1H = (
    "Чтобы бот начал работать, тебе нужно *выбрать режим*.\n"
    "Определяйся: *Daily* или *By mood* — и погнали 🧡"
)

MODE_REMINDER_AFTER_START_24H = (
    "Ты все еще не выбрал режим...\n\n"
    "Нажми *Daily* или *By mood* — это займёт один миг"
)

MODE_REMINDER_ON_MODE_SCREEN_1H = (
    "Чтобы бот начал работать, тебе нужно *выбрать режим*.\n"
    "Определяйся: *Daily* или *By mood* — и погнали 🧡"
)

MODE_REMINDER_ON_MODE_SCREEN_24H = MODE_REMINDER_AFTER_START_24H

TIME_REMINDER_AFTER_DAILY_PICK_1H = (
    "Мы уже почти готовы начать долгий и счастливый путь к движению, осталось выбрать время, "
    "когда хочешь получать сообщения\n\n"
    "*Введи время в формате ЧЧ.ММ (например, 09.30)*"
)

TIME_REMINDER_AFTER_DAILY_PICK_24H = (
    "Эй, мы так и не начали\n"
    "Если не выберешь время сегодня, придётся отложить старт..а жаль, тебя ждет отличное занятие!\n\n"
    "*Введи время в формате ЧЧ.ММ (например, 09.30)*"
)

TIME_REMINDER_AFTER_TIME_BUTTON_1H = TIME_REMINDER_AFTER_DAILY_PICK_1H

TIME_REMINDER_AFTER_TIME_BUTTON_24H = TIME_REMINDER_AFTER_DAILY_PICK_24H


def _mode_start_job_names(user_id: int) -> list[str]:
    return [f"mode_start_reminder_1h_{user_id}", f"mode_start_reminder_24h_{user_id}"]


def _mode_pick_job_names(user_id: int) -> list[str]:
    return [f"mode_pick_reminder_1h_{user_id}", f"mode_pick_reminder_24h_{user_id}"]


def _time_pick_job_names(user_id: int) -> list[str]:
    return [f"time_pick_reminder_1h_{user_id}", f"time_pick_reminder_24h_{user_id}"]


def _time_input_job_names(user_id: int) -> list[str]:
    return [f"time_input_reminder_1h_{user_id}", f"time_input_reminder_24h_{user_id}"]


async def _cancel_named_jobs(context: ContextTypes.DEFAULT_TYPE, job_names: list[str]) -> None:
    if not hasattr(context, "job_queue") or context.job_queue is None:
        return
    job_queue = context.job_queue
    for job_name in job_names:
        try:
            for job in job_queue.get_jobs_by_name(job_name):
                job.schedule_removal()
        except Exception as e:
            print(f"Ошибка отмены задачи '{job_name}': {e}")
    try:
        scheduler = job_queue.scheduler
        for job_name in job_names:
            try:
                if scheduler.get_job(job_name):
                    scheduler.remove_job(job_name)
            except Exception:
                pass
    except Exception as e:
        print(f"Ошибка доступа к scheduler: {e}")


async def strip_inline_keyboard(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: Optional[int]
) -> None:
    if not message_id:
        return
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None
        )
    except Exception as e:
        print(f"Не удалось снять inline-кнопки с сообщения {message_id}: {e}")


async def _send_reminder_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_markup=None,
) -> None:
    await context.bot.send_message(
        chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


def _remember_onboarding_keyboard_state(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    keyboard_kind: str,
):
    """Сохраняет сообщение и тип кнопок, чтобы напоминание могло их продублировать."""
    context.user_data["onboarding_keyboard_chat_id"] = chat_id
    context.user_data["onboarding_keyboard_message_id"] = message_id
    context.user_data["onboarding_keyboard_kind"] = keyboard_kind


async def _remove_previous_onboarding_keyboard(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Убирает inline-кнопки с предыдущего шага онбординга, если они еще есть."""
    prev_chat_id = context.user_data.get("onboarding_keyboard_chat_id")
    prev_message_id = context.user_data.get("onboarding_keyboard_message_id")
    if prev_chat_id != chat_id or not prev_message_id:
        return
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=prev_message_id,
            reply_markup=None,
        )
    except Exception as e:
        print(f"Не удалось убрать предыдущие onboarding-кнопки: {e}")


async def send_mode_start_reminder_1h(context: ContextTypes.DEFAULT_TYPE):
    """+1 ч после /start: режим не выбран."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    if not _is_mode_choice_pending(user_id):
        return
    try:
        await _send_reminder_message(
            context,
            chat_id,
            MODE_REMINDER_AFTER_START_1H,
            reply_markup=get_start_onboarding_keyboard(),
        )
    except Exception as e:
        print(f"Ошибка напоминания о режиме после /start (1ч): {e}")


async def send_mode_start_reminder_24h(context: ContextTypes.DEFAULT_TYPE):
    """+24 ч после /start: режим не выбран."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    if not _is_mode_choice_pending(user_id):
        return
    try:
        await _send_reminder_message(
            context,
            chat_id,
            MODE_REMINDER_AFTER_START_24H,
            reply_markup=get_mode_choice_keyboard(),
        )
    except Exception as e:
        print(f"Ошибка напоминания о режиме после /start (24ч): {e}")


async def send_mode_pick_reminder_1h(context: ContextTypes.DEFAULT_TYPE):
    """+1 ч после «Выбрать режим»: Daily/By mood не нажаты."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    if not _is_mode_choice_pending(user_id):
        return
    try:
        await _send_reminder_message(
            context,
            chat_id,
            MODE_REMINDER_ON_MODE_SCREEN_1H,
            reply_markup=get_mode_choice_keyboard(),
        )
    except Exception as e:
        print(f"Ошибка напоминания на экране режима (1ч): {e}")


async def send_mode_pick_reminder_24h(context: ContextTypes.DEFAULT_TYPE):
    """+24 ч после «Выбрать режим»: Daily/By mood не нажаты."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    if not _is_mode_choice_pending(user_id):
        return
    try:
        await _send_reminder_message(
            context,
            chat_id,
            MODE_REMINDER_ON_MODE_SCREEN_24H,
            reply_markup=get_mode_choice_keyboard(),
        )
    except Exception as e:
        print(f"Ошибка напоминания на экране режима (24ч): {e}")


async def send_time_pick_reminder_1h(context: ContextTypes.DEFAULT_TYPE):
    """+1 ч после Daily/Challenge: кнопку «Выбрать время» не нажали."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    if not _is_daily_time_onboarding_pending(user_id):
        return
    try:
        await strip_inline_keyboard(
            context, chat_id, job.data.get("strip_message_id")
        )
        await _send_reminder_message(
            context, chat_id, TIME_REMINDER_AFTER_DAILY_PICK_1H
        )
    except Exception as e:
        print(f"Ошибка напоминания о времени после Daily (1ч): {e}")


async def send_time_pick_reminder_24h(context: ContextTypes.DEFAULT_TYPE):
    """+24 ч после Daily/Challenge: кнопку «Выбрать время» не нажали."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    if not _is_daily_time_onboarding_pending(user_id):
        return
    try:
        await strip_inline_keyboard(
            context, chat_id, job.data.get("strip_message_id")
        )
        await _send_reminder_message(
            context, chat_id, TIME_REMINDER_AFTER_DAILY_PICK_24H
        )
    except Exception as e:
        print(f"Ошибка напоминания о времени после Daily (24ч): {e}")


async def send_time_input_reminder_1h(context: ContextTypes.DEFAULT_TYPE):
    """+1 ч после «Выбрать время»: время не введено."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    if not _is_daily_time_onboarding_pending(user_id):
        return
    try:
        await _send_reminder_message(
            context, chat_id, TIME_REMINDER_AFTER_TIME_BUTTON_1H
        )
    except Exception as e:
        print(f"Ошибка напоминания о вводе времени (1ч): {e}")


async def send_time_input_reminder_24h(context: ContextTypes.DEFAULT_TYPE):
    """+24 ч после «Выбрать время»: время не введено."""
    job = context.job
    chat_id = job.data["chat_id"]
    user_id = job.data["user_id"]
    if not _is_daily_time_onboarding_pending(user_id):
        return
    try:
        await _send_reminder_message(
            context, chat_id, TIME_REMINDER_AFTER_TIME_BUTTON_24H
        )
    except Exception as e:
        print(f"Ошибка напоминания о вводе времени (24ч): {e}")


async def schedule_mode_reminders(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Напоминания о выборе режима через 1 и 24 ч после /start."""
    if not hasattr(context, "job_queue") or context.job_queue is None:
        print("JobQueue недоступен — напоминания о выборе режима не будут отправлены")
        return

    await cancel_mode_reminders(context, user_id)
    job_data = {"chat_id": chat_id, "user_id": user_id}
    try:
        context.job_queue.run_once(
            send_mode_start_reminder_1h,
            when=timedelta(hours=1),
            data=job_data,
            name=f"mode_start_reminder_1h_{user_id}",
        )
        context.job_queue.run_once(
            send_mode_start_reminder_24h,
            when=timedelta(hours=24),
            data=job_data,
            name=f"mode_start_reminder_24h_{user_id}",
        )
    except Exception as e:
        print(f"Ошибка планирования напоминаний о режиме после /start: {e}")


async def schedule_mode_pick_reminders(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int
):
    """Напоминания через 1 и 24 ч после «Выбрать режим» (экран Daily / By mood)."""
    if not hasattr(context, "job_queue") or context.job_queue is None:
        return

    await _cancel_named_jobs(context, _mode_start_job_names(user_id))
    await _cancel_named_jobs(context, _mode_pick_job_names(user_id))

    job_data = {"chat_id": chat_id, "user_id": user_id}
    try:
        context.job_queue.run_once(
            send_mode_pick_reminder_1h,
            when=timedelta(hours=1),
            data=job_data,
            name=f"mode_pick_reminder_1h_{user_id}",
        )
        context.job_queue.run_once(
            send_mode_pick_reminder_24h,
            when=timedelta(hours=24),
            data=job_data,
            name=f"mode_pick_reminder_24h_{user_id}",
        )
    except Exception as e:
        print(f"Ошибка планирования напоминаний на экране режима: {e}")


async def cancel_mode_reminders(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Отменяет все напоминания о выборе режима."""
    await _cancel_named_jobs(
        context,
        _mode_start_job_names(user_id)
        + _mode_pick_job_names(user_id)
        + [f"mode_reminder_1h_{user_id}", f"mode_reminder_24h_{user_id}"],
    )


async def schedule_time_pick_reminders(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    welcome_message_id: Optional[int],
):
    """Напоминания о времени: выбрали Daily/Challenge, но не нажали «Выбрать время»."""
    if not hasattr(context, "job_queue") or context.job_queue is None:
        print("JobQueue недоступен — напоминания о времени не будут отправлены")
        return

    await _cancel_named_jobs(context, _time_pick_job_names(user_id))
    await _cancel_named_jobs(context, _time_input_job_names(user_id))

    job_data = {
        "chat_id": chat_id,
        "user_id": user_id,
        "strip_message_id": welcome_message_id,
    }
    try:
        context.job_queue.run_once(
            send_time_pick_reminder_1h,
            when=timedelta(hours=1),
            data=job_data,
            name=f"time_pick_reminder_1h_{user_id}",
        )
        context.job_queue.run_once(
            send_time_pick_reminder_24h,
            when=timedelta(hours=24),
            data=job_data,
            name=f"time_pick_reminder_24h_{user_id}",
        )
    except Exception as e:
        print(f"Ошибка планирования напоминаний о времени (Daily): {e}")


async def schedule_reminders(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Напоминания о времени: нажали «Выбрать время», но не ввели."""
    if not hasattr(context, "job_queue") or context.job_queue is None:
        print("JobQueue недоступен — напоминания не будут отправлены")
        return

    await _cancel_named_jobs(context, _time_pick_job_names(user_id))
    await _cancel_named_jobs(context, _time_input_job_names(user_id))

    job_data = {"chat_id": chat_id, "user_id": user_id}
    try:
        context.job_queue.run_once(
            send_time_input_reminder_1h,
            when=timedelta(hours=1),
            data=job_data,
            name=f"time_input_reminder_1h_{user_id}",
        )
        context.job_queue.run_once(
            send_time_input_reminder_24h,
            when=timedelta(hours=24),
            data=job_data,
            name=f"time_input_reminder_24h_{user_id}",
        )
    except Exception as e:
        print(f"Ошибка планирования напоминаний о вводе времени: {e}")


async def cancel_reminders(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Отменяет все напоминания о выборе времени в онбординге."""
    await _cancel_named_jobs(
        context, _time_pick_job_names(user_id) + _time_input_job_names(user_id)
    )
    # Старые имена задач (до рефакторинга)
    await _cancel_named_jobs(
        context, [f"reminder_1h_{user_id}", f"reminder_24h_{user_id}"]
    )


async def remove_callback_keyboard(query):
    """Убирает inline-кнопки с сообщения, по которому пользователь уже сделал выбор."""
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        print(f"Не удалось убрать inline-кнопки после callback {query.data}: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start: сброс и первый экран онбординга."""
    context.user_data.pop('waiting_for_practice_suggestion', None)
    context.user_data.pop('waiting_for_time', None)
    context.user_data.pop('is_time_change', None)
    context.user_data.pop('waiting_for_challenge_time', None)
    context.user_data.pop('pending_challenge_practice_id', None)
    context.user_data.pop("onboarding_keyboard_chat_id", None)
    context.user_data.pop("onboarding_keyboard_message_id", None)
    context.user_data.pop("onboarding_keyboard_kind", None)

    user = update.effective_user
    chat_id = update.effective_chat.id

    from data.db import set_user_onboarding_required
    set_user_onboarding_required(
        user.id,
        chat_id,
        user_name=user.first_name,
        user_nickname=user.username,
    )

    intro = (
        f"Привет, *{user.first_name}* 🧡\n\n"
        "Я, твой YogaDailyBot, помогу тебе чаще двигаться и не терять контакт с телом 🔋\n\n"
        "Со мной тебе не нужно будет тратить время на поиск, ведь я храню *большой каталог самых приятных практик* от разных преподавателей с YouTube, в том числе от владельца бота @strello4ka.\n"
        "Каталог постоянно растет и обновляется, а *практики подобраны разнообразно:* бодрящая разминка на все тело, изолированная на пресс, "
        "здоровая спина, релакс вытяжение...перечислять можно долго, это все указывается в описании практики.\n"
        "Больше никакого скроллинга YouTube - просто открой сообщение и разомнись!\n\n"
        "У меня *есть несколько режимов работы* для выбора под твой запрос и образ жизни.\n\n"
        "Далее ты можешь посмотреть пример практики или сразу *перейти к выбору режима* 👇"
    )

    msg = update.effective_message
    if not msg:
        return
    clear_keyboard_message = await msg.reply_text(
        "...",
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=clear_keyboard_message.message_id,
        )
    except Exception:
        pass
    intro_message = await msg.reply_text(
        intro,
        reply_markup=get_start_onboarding_keyboard(),
        parse_mode='Markdown',
    )
    _remember_onboarding_keyboard_state(
        context=context,
        chat_id=chat_id,
        message_id=intro_message.message_id,
        keyboard_kind="start_onboarding",
    )

    await schedule_mode_reminders(context, chat_id, user.id)


async def onboarding_open_mode_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход к выбору режима с экрана /start и после просмотра примера."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await remove_callback_keyboard(query)
    chat_id = update.effective_chat.id
    mode_choice_message = await context.bot.send_message(
        chat_id=chat_id,
        text=MODE_CHOICE_INTRO_MARKDOWN,
        reply_markup=get_mode_choice_keyboard(),
        parse_mode='Markdown',
    )
    _remember_onboarding_keyboard_state(
        context=context,
        chat_id=chat_id,
        message_id=mode_choice_message.message_id,
        keyboard_kind="mode_choice",
    )

    user = update.effective_user
    if user:
        await schedule_mode_pick_reminders(context, chat_id, user.id)


async def onboarding_show_example_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет пример практики без влияния на прогресс и расписание."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await remove_callback_keyboard(query)
    chat_id = update.effective_chat.id

    weekday = get_current_weekday()
    sample = get_yoga_practice_by_weekday_order(weekday, 1)
    if not sample:
        fallback_message = await context.bot.send_message(
            chat_id=chat_id,
            text="Не смог подобрать пример практики, но ты можешь сразу перейти к выбору режима 👇",
            reply_markup=get_choose_mode_keyboard(),
        )
        _remember_onboarding_keyboard_state(
            context=context,
            chat_id=chat_id,
            message_id=fallback_message.message_id,
            keyboard_kind="choose_mode",
        )
        return

    (
        _practice_id,
        _title,
        video_url,
        time_practices,
        channel_name,
        _description,
        my_description,
        intensity,
        _practice_weekday,
        _created_at,
        _updated_at,
    ) = sample
    text = format_practice_message(
        title="Практика дня",
        my_description=my_description,
        time_practices=time_practices,
        intensity=intensity,
        channel_name=channel_name,
        video_url=video_url,
    )
    example_message = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='Markdown',
        disable_web_page_preview=False,
        reply_markup=get_choose_mode_keyboard(),
    )
    _remember_onboarding_keyboard_state(
        context=context,
        chat_id=chat_id,
        message_id=example_message.message_id,
        keyboard_kind="choose_mode",
    )


async def mode_pick_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь выбрал Daily — показываем описание программы и кнопку «Выбрать время»."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await remove_callback_keyboard(query)
    user = update.effective_user
    chat_id = update.effective_chat.id

    await cancel_mode_reminders(context, user.id)
    context.user_data.pop("onboarding_keyboard_chat_id", None)
    context.user_data.pop("onboarding_keyboard_message_id", None)
    context.user_data.pop("onboarding_keyboard_kind", None)

    from data.db import get_user_bot_mode, set_user_daily_pending

    prev = get_user_bot_mode(user.id)
    if prev == "daily":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Ты уже в режиме *Daily*. Время рассылки можно поменять по кнопке «Изменить время» на клавиатуре.",
            parse_mode="Markdown",
        )
        return
    if prev in ("by_mood", "challenge", "pending"):
        set_user_daily_pending(user.id)
    if prev in ("by_mood", "challenge"):
        from app.mode.extra_practices import strip_extra_practices_inline_keyboards

        await strip_extra_practices_inline_keyboards(context.bot, user.id)
        clear_keyboard_message = await context.bot.send_message(
            chat_id=chat_id,
            text="...",
            reply_markup=ReplyKeyboardRemove(),
        )
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=clear_keyboard_message.message_id,
            )
        except Exception:
            pass
    welcome_text_1 = (
        f"Ты выбрал мой любимый режим - *Daily* 🧡\n\n"
         "Каждая неделя содержит практики: \n"
        "🌀 2-3 бодрые, 5-15 минут\n"
        "🌀 по вторникам - всегда работа с осанкой, спиной и шеей\n"
        "🌀 по пятницам - что-то необычное для развития кругозора и получения нового опыта\n"
        "🌀 по субботам - горячая активная, 20-25 минут\n" 
        "🌀 по воскресеньям - релакс, 20-25 минут\n"
        "🌀 плюс бонус - приходит один раз в неделю в дополнение к основной практике: дыхательная техника, медитация, отстройка асан, изучение балансов на руках.\n\n"
        "Осталось *выбрать время* и можно начинать наш YogaDaily путь!"    )
    time_choice_message = await context.bot.send_message(
        chat_id=chat_id,
        text=welcome_text_1,
        reply_markup=get_welcome_keyboard(),
        parse_mode='Markdown',
    )
    context.user_data["daily_time_choice_chat_id"] = chat_id
    context.user_data["daily_time_choice_message_id"] = time_choice_message.message_id

    if hasattr(context, "job_queue") and context.job_queue is not None:
        await schedule_time_pick_reminders(
            context, chat_id, user.id, time_choice_message.message_id
        )


async def mode_pick_by_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Режим By mood: без рассылки по времени, сразу клавиатура фильтров."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    await remove_callback_keyboard(query)
    user = update.effective_user
    chat_id = update.effective_chat.id

    await cancel_mode_reminders(context, user.id)
    await cancel_reminders(context, user.id)
    context.user_data.pop("onboarding_keyboard_chat_id", None)
    context.user_data.pop("onboarding_keyboard_message_id", None)
    context.user_data.pop("onboarding_keyboard_kind", None)

    from data.db import get_user_bot_mode
    prev_mode = get_user_bot_mode(user.id)

    if prev_mode == "by_mood":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Ты уже в режиме *By mood*. Выбирай практику по настроению с помощью кнопок на клавиатуре.",
            parse_mode="Markdown",
            reply_markup=get_by_mood_reply_keyboard(),
        )
        return
    activate_user_by_mood(
        user.id,
        chat_id,
        user_name=user.first_name,
        user_nickname=user.username,
    )
    from data.db import touch_by_mood_activity
    touch_by_mood_activity(user.id)
    from app.mode.extra_practices import strip_extra_practices_inline_keyboards

    await strip_extra_practices_inline_keyboards(context.bot, user.id)
    context.user_data.pop('waiting_for_time', None)
    context.user_data.pop('is_time_change', None)
    text = (
        "Ты выбрал режим - *By mood* 🧡 \n\n"
        "Внизу у тебя *появились кнопки* для выбора практики по настроению:\n"
        "🌀 *Практика дня* — рандом из каталога, доверься мне, я выберу что-то хорошее\n"
        "🌀 *Без коврика* — где бы ты ни был, движение всегда рядом\n"
        "🌀 *Ленивые дни* — когда ты почти овощ, но очень осознанный овощ\n"
        "🌀 *Мини* — отсутствие времени больше не проблема\n"
        "🌀 *Хард* — когда хочется почувствовать свою мощь\n"
        "🌀 *Сам решу* — выбираешь время, потом интенсивность, а я подбираю практику\n\n"
        "Также есть *Меню* ↙️, где можно посмотреть свой прогресс, задонатить и найти другую полезную инфу.\n\n"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='Markdown',
        reply_markup=get_by_mood_reply_keyboard(),
        disable_web_page_preview=True,
    )


async def want_start_callback(update: Update, context: CallbackContext):
    """Обработчик нажатия кнопки "Выбрать время".
    
    Показывает пользователю инструкцию по вводу времени и сразу запрашивает ввод.
    Планирует напоминания через 1 и 24 часа.
    Это второй шаг в онбординге.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    print("=== want_start_callback вызван ===")
    
    # Получаем callback query (нажатие кнопки)
    query = update.callback_query
    print(f"Callback data: {query.data}")

    user_id = update.effective_user.id
    from app.mode.challenge import (
        PENDING_CHALLENGE_PRACTICE_KEY,
        handle_challenge_time_choice_callback,
    )
    from data.db import get_user_bot_mode, is_user_onboarding_required

    if (
        context.user_data.get(PENDING_CHALLENGE_PRACTICE_KEY)
        or (
            get_user_bot_mode(user_id) == "challenge"
            and is_user_onboarding_required(user_id)
        )
    ):
        await handle_challenge_time_choice_callback(update, context)
        return
    
    # Отвечаем на callback, чтобы убрать "часики" у кнопки
    await query.answer()
    await remove_callback_keyboard(query)

    chat_id = update.effective_chat.id
    strip_message_id = context.user_data.pop("daily_time_choice_message_id", None)
    context.user_data.pop("daily_time_choice_chat_id", None)
    await strip_inline_keyboard(context, chat_id, strip_message_id)
    
    # Очищаем другие состояния перед установкой нового
    context.user_data.pop('waiting_for_practice_suggestion', None)
    # Важно: явно удаляем флаг is_time_change, чтобы гарантировать онбординг,
    # а не изменение времени (флаг мог остаться от предыдущих действий)
    context.user_data.pop('is_time_change', None)
    
    # Устанавливаем состояние ожидания ввода времени
    context.user_data['waiting_for_time'] = True
    
    # Сообщение о вводе времени
    time_input_text = (
        "*Последний шаг!*\n\n"
        "Давай выберем время, в которое ты хочешь получать ежедневные практики.\n\n"
        "*Введи время в формате ЧЧ.ММ (например, 09.30)*\n\n"
        "PS. Время учитывается по МСК"
    )
    
    # Отправляем новое сообщение (не редактируем старое)
    await context.bot.send_message(
        chat_id=chat_id,
        text=time_input_text,
        parse_mode='Markdown'
    )
    
    # Планируем напоминания через 1 и 24 часа (если JobQueue доступен)
    if hasattr(context, 'job_queue') and context.job_queue is not None:
        await schedule_reminders(context, chat_id, user_id)
    else:
        print("JobQueue недоступен - напоминания не будут отправлены")


async def handle_time_input(update: Update, context: CallbackContext):
    """Обработчик ввода времени для онбординга (первый ввод времени).
    
    Валидирует введенное время и сохраняет его.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    print(f"=== DEBUG: handle_time_input (онбординг) вызвана ===")
    print(f"User data: {context.user_data}")
    print(f"Waiting for time: {context.user_data.get('waiting_for_time')}")
    print(f"Is time change: {context.user_data.get('is_time_change')}")
    
    if context.user_data.get("is_time_change"):
        print("=== DEBUG: Это изменение времени, не онбординг ===")
        return

    user_id = update.effective_user.id if update.effective_user else None
    from data.db import is_user_onboarding_required

    if not context.user_data.get("waiting_for_time"):
        if not user_id or not is_user_onboarding_required(user_id):
            print("=== DEBUG: Пользователь не в состоянии ожидания времени ===")
            return

    time_input = update.message.text
    print(f"=== DEBUG: Введенное время: '{time_input}' ===")
    
    # Валидируем формат времени
    is_valid, result = validate_time_format(time_input)
    
    if not is_valid:
        await update.message.reply_text(
            f"🚨 {result}\n\n"
            "Попробуй еще раз в формате *ЧЧ.ММ*",
            parse_mode="Markdown",
        )
        return
    
    # Время валидно, сохраняем его
    selected_time = result
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Убираем состояние ожидания
    context.user_data.pop('waiting_for_time', None)
    
    # Отменяем запланированные напоминания
    await cancel_reminders(context, user_id)
    
    # Сохраняем время в базу данных
    from data.db import save_user_time
    user_name = update.effective_user.first_name
    user_nickname = update.effective_user.username  # Никнейм пользователя из Telegram
    save_success = save_user_time(user_id, chat_id, selected_time, user_name, user_nickname=user_nickname)
    
    if not save_success:
        print(f"Ошибка сохранения времени пользователя {user_id} в БД")

    # TODO: Настроить расписание для отправки
    # await schedule_daily_message(user_id, selected_time)

    # Сообщение для онбординга (первый ввод времени)
    success_text = (
        f"Готово ✔️\n\n"
        f"Твое время *{selected_time}*.\n"
        "Начиная с *завтрашнего дня*, практики будут приходить ежедневно в выбранное тобой время автоматически.\n\n"
        "А сейчас ознакомься с новыми кнопками 👇"
    )
    
    # Отправляем сообщение об успешной настройке (без кнопок)
    await update.message.reply_text(
        success_text,
        parse_mode='Markdown',
        disable_web_page_preview=True  # Отключаем превью видео
    )
    
    # Также показываем Reply-клавиатуру для удобства
    from .keyboards import get_main_reply_keyboard
    await update.message.reply_text(
        "Внизу у тебя *появились кнопки* режима Daily:\n\n"
        "🕓 *Изменить время* — жми, чтобы изменить время рассылки\n"
        "💡 *Советы* — жми обязательно\n"
        "🪫 *Пауза* — приостановить или возобновить ежедневную рассылку\n"
        "✨ *Еще практики* — дополнительные практики по настроению (как в режиме By mood, но без отключения ежедневной рассылки)\n\n"
        "Также есть *Меню* ↙️, где можно посмотреть свой прогресс, задонатить и найти другую полезную инфу\n\n",
        reply_markup=get_main_reply_keyboard(),
        parse_mode='Markdown',
        disable_web_page_preview=True  # Отключаем предпросмотр видео
    )




async def back_to_hours_callback(update: Update, context: CallbackContext):
    """Обработчик кнопки "Назад к часам" - больше не используется.
    
    Оставлен для совместимости, но не вызывается.
    """
    pass

