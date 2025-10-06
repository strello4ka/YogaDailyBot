"""/start and onboarding handler for YogaDailyBot.
старт и онбординг.
"""

import asyncio
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext
from .keyboards import get_welcome_keyboard


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


async def send_reminder_4h(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет напоминание через 4 часа после выбора времени.
    
    Args:
        context: Контекст бота с данными пользователя
    """
    job = context.job
    chat_id = job.data['chat_id']
    user_id = job.data['user_id']
    
    reminder_text = (
        "Мы уже почти готовы начать долгий и счастливый путь к движению, "
        "осталось выбрать время, когда хочешь получать сообщения"
    )
    
    try:
        await context.bot.send_message(chat_id, reminder_text)
    except Exception as e:
        print(f"Ошибка отправки напоминания 4ч: {e}")


async def send_reminder_24h(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет напоминание через 24 часа после выбора времени.
    
    Args:
        context: Контекст бота с данными пользователя
    """
    job = context.job
    chat_id = job.data['chat_id']
    user_id = job.data['user_id']
    
    reminder_text = (
        "Эй, мы так и не начали\n"
        "Если не выберешь время сегодня, придётся отложить старт..а жаль, тебя ждет отличное занятие!"
    )
    
    try:
        await context.bot.send_message(chat_id, reminder_text)
    except Exception as e:
        print(f"Ошибка отправки напоминания 24ч: {e}")


async def schedule_reminders(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Планирует отправку напоминаний через 4 и 24 часа.
    
    Args:
        context: Контекст бота
        chat_id: ID чата пользователя
        user_id: ID пользователя
    """
    # Проверяем, что JobQueue доступен
    if not hasattr(context, 'job_queue') or context.job_queue is None:
        print("JobQueue недоступен - напоминания не будут отправлены")
        return
    
    job_data = {'chat_id': chat_id, 'user_id': user_id}
    
    try:
        # Планируем напоминание через 4 часа
        context.job_queue.run_once(
            send_reminder_4h,
            when=timedelta(hours=4),
            data=job_data,
            name=f"reminder_4h_{user_id}"
        )
        
        # Планируем напоминание через 24 часа
        context.job_queue.run_once(
            send_reminder_24h,
            when=timedelta(hours=24),
            data=job_data,
            name=f"reminder_24h_{user_id}"
        )
    except Exception as e:
        print(f"Ошибка планирования напоминаний: {e}")


async def cancel_reminders(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Отменяет запланированные напоминания при выборе времени.
    
    Args:
        context: Контекст бота
        user_id: ID пользователя
    """
    # Проверяем, что JobQueue доступен
    if not hasattr(context, 'job_queue') or context.job_queue is None:
        print("JobQueue недоступен - не можем отменить напоминания")
        return
    
    try:
        # Удаляем задачи напоминаний (если они существуют)
        try:
            context.job_queue.scheduler.remove_job(f"reminder_4h_{user_id}")
        except:
            pass  # Задача уже удалена или не существует
        
        try:
            context.job_queue.scheduler.remove_job(f"reminder_24h_{user_id}")
        except:
            pass  # Задача уже удалена или не существует
            
    except Exception as e:
        print(f"Ошибка отмены напоминаний: {e}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start - приветствие пользователя.
    
    Отправляет два приветственных сообщения:
    1. Описание бота и его возможностей
    2. Пример практики с кнопкой "выбрать время"
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Получаем информацию о пользователе
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Первое сообщение - описание бота
    welcome_text_1 = (
        f"Привет, {user.first_name}!\n"
        "Вот пример ежедневной практики:\n"
        "▶️ [Youtube](https://youtu.be/oTzetTgYpSU?si=_V8LNx3i3Iq5zeoH)\n"
        "*для просмотра потребуется vpn*\n\n"
        "Если хочешь получать такие каждый день - выбирай время и погнали! Больше никакого скроллинга YouTube - просто открой сообщение и разомнись"
    )
    
    # Отправляем первое сообщение
    
    await update.message.reply_text(
        welcome_text_1,
        reply_markup=get_welcome_keyboard(),
        parse_mode='Markdown'
    )


async def want_start_callback(update: Update, context: CallbackContext):
    """Обработчик нажатия кнопки "Выбрать время".
    
    Показывает пользователю инструкцию по вводу времени и сразу запрашивает ввод.
    Планирует напоминания через 4 и 24 часа.
    Это второй шаг в онбординге.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    print("=== want_start_callback вызван ===")
    
    # Получаем callback query (нажатие кнопки)
    query = update.callback_query
    print(f"Callback data: {query.data}")
    
    # Отвечаем на callback, чтобы убрать "часики" у кнопки
    await query.answer()
    
    # Получаем данные пользователя
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Очищаем другие состояния перед установкой нового
    context.user_data.pop('waiting_for_practice_suggestion', None)
    
    # Устанавливаем состояние ожидания ввода времени
    context.user_data['waiting_for_time'] = True
    
    # Сообщение о вводе времени
    time_input_text = (
        "Супер!\n"
        "Давай выберем время, в которое ты хочешь получать сообщения, рассылка начнется с завтрашнего дня.\n"
        "*Введи время в формате ЧЧ.ММ (например, 09.30)*\n\n"
        "время учитывается по мск"
    )
    
    # Отправляем новое сообщение (не редактируем старое)
    await context.bot.send_message(
        chat_id=chat_id,
        text=time_input_text,
        parse_mode='Markdown'
    )
    
    # Планируем напоминания через 4 и 24 часа (если JobQueue доступен)
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
    
    # Проверяем, что пользователь в состоянии ожидания ввода времени
    # И что это НЕ изменение времени (для онбординга)
    if not context.user_data.get('waiting_for_time') or context.user_data.get('is_time_change'):
        print("=== DEBUG: Пользователь не в состоянии ожидания времени ИЛИ это изменение времени ===")
        return
    
    # Получаем введенное время
    time_input = update.message.text
    print(f"=== DEBUG: Введенное время: '{time_input}' ===")
    
    # Валидируем формат времени
    is_valid, result = validate_time_format(time_input)
    
    if not is_valid:
        # Показываем ошибку и просим ввести заново
        await update.message.reply_text(
            f"❌ {result}\n\n"
            "Попробуй еще раз в формате ЧЧ.ММ"
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
    from data.postgres_db import save_user_time, get_current_weekday
    user_name = update.effective_user.first_name
    onboarding_weekday = get_current_weekday()  # Получаем текущий день недели
    save_success = save_user_time(user_id, chat_id, selected_time, user_name, onboarding_weekday=onboarding_weekday)
    
    if not save_success:
        print(f"Ошибка сохранения времени пользователя {user_id} в БД")
    
    # TODO: Настроить расписание для отправки
    # await schedule_daily_message(user_id, selected_time)
    
    # Сообщение для онбординга (первый ввод времени)
    success_text = (
        f"Готово!\n"
        f"Твое время для практики: **{selected_time}**\n"
        "Начиная с завтрашнего дня, я буду присылать тебе ссылку на видео в это время автоматически.\n"
        "Изменить время можно в любой момент в меню.\n\n"
        "А если не терпится начать прямо сейчас,[выполни практику из примера](https://youtu.be/oTzetTgYpSU?si=_V8LNx3i3Iq5zeoH)\n\n"
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
        "Для быстрого доступа используй кнопки ниже:\n"
        "- Изменить время - жми, чтобы изменить время рассылки\n"
        "- Предложить практику - жми, если хочешь поделиться ссылкои на практику, и она появится в боте\n"
        "- Советы - жми, чтобы получить рекомендации по использованию бота\n"
        "- Донаты - мой бот бесплатный, но если ты прекрасный человек и хочешь поддержать развитие проекта, жми",
        reply_markup=get_main_reply_keyboard(),
        parse_mode='Markdown'
    )




async def back_to_hours_callback(update: Update, context: CallbackContext):
    """Обработчик кнопки "Назад к часам" - больше не используется.
    
    Оставлен для совместимости, но не вызывается.
    """
    pass


async def cancel_time_callback(update: Update, context: CallbackContext):
    """Обработчик отмены ввода времени.
    
    Отменяет напоминания и возвращает пользователя к началу онбординга.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    query = update.callback_query
    await query.answer()
    
    # Получаем ID пользователя для отмены напоминаний
    user_id = update.effective_user.id
    
    # Отменяем запланированные напоминания
    await cancel_reminders(context, user_id)
    
    # Убираем состояние ожидания ввода времени
    context.user_data.pop('waiting_for_time', None)
    
    # Возвращаемся к приветствию
    await start_command(update, context)



