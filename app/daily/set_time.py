"""Handlers for selecting and saving preferred delivery time."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from app.config import DEFAULT_TZ
from app.schedule.scheduler import send_practice_to_user
from data.db import get_current_weekday, get_user_notify_time


MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)


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


async def handle_set_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Изменить время'.
    
    Запускает процесс изменения времени доставки уведомлений.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    print(f"=== DEBUG: handle_set_time_callback вызвана ===")
    print(f"User data до изменений: {context.user_data}")
    
    # Отвечаем на callback query если это inline кнопка
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Очищаем другие состояния перед установкой нового
    context.user_data.pop('waiting_for_practice_suggestion', None)
    
    # Устанавливаем состояние ожидания ввода времени
    context.user_data['waiting_for_time'] = True
    # Устанавливаем флаг, что это изменение времени, а не онбординг
    context.user_data['is_time_change'] = True
    print(f"=== DEBUG: Установлено состояние waiting_for_time = True и is_time_change = True ===")
    print(f"User data после изменений: {context.user_data}")
    
    # Получаем chat_id
    chat_id = update.effective_chat.id
    
    # Сообщение о вводе нового времени
    time_input_text = (
        "Введи новое время *в формате ЧЧ.ММ* (например, 09.30)\n\n"
        "PS. Время учитывается по МСК и обновиться завтра"
    )
    
    # Отправляем сообщение
    await context.bot.send_message(
        chat_id=chat_id,
        text=time_input_text,
        parse_mode='Markdown'
    )


async def handle_time_change_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода времени для изменения времени доставки.
    
    Валидирует введенное время и сохраняет его.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    print(f"=== DEBUG: handle_time_change_input вызвана ===")
    print(f"User data: {context.user_data}")
    print(f"Waiting for time: {context.user_data.get('waiting_for_time')}")
    
    # Проверяем, что пользователь в состоянии ожидания ввода времени
    if not context.user_data.get('waiting_for_time'):
        print("=== DEBUG: Пользователь не в состоянии ожидания времени ===")
        return
    
    # Получаем введенное время
    time_input = update.message.text
    print(f"=== DEBUG: Введенное время: '{time_input}' ===")
    
    # Валидируем формат времени
    is_valid, result = validate_time_format(time_input)
    
    if not is_valid:
        # Показываем ошибку и просим ввести заново
        await update.message.reply_text(
            f"🚨 {result}\n\n"
            "Попробуй еще раз в формате ЧЧ.ММ"
        )
        return
    
    # Время валидно, сохраняем его
    selected_time = result
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Получаем предыдущее время уведомлений пользователя до изменения
    old_notify_time = get_user_notify_time(user_id)

    # Убираем состояние ожидания
    context.user_data.pop('waiting_for_time', None)
    context.user_data.pop('is_time_change', None)

    # Сохраняем время в базу данных БЕЗ обнуления счетчика дней
    from data.db import save_user_time
    user_name = update.effective_user.first_name
    user_nickname = update.effective_user.username  # Никнейм пользователя из Telegram
    save_success = save_user_time(
        user_id,
        chat_id,
        selected_time,
        user_name,
        user_nickname=user_nickname,
        reset_days=False,
    )

    if not save_success:
        print(f"Ошибка сохранения времени пользователя {user_id} в БД")

    # Если пользователь изменил время ДО того, как должна была прийти сегодняшняя практика,
    # гарантируем, что она всё равно придёт по старому времени один раз.
    try:
        if (
            save_success
            and old_notify_time
            and old_notify_time != selected_time
            and hasattr(context, "job_queue")
            and context.job_queue is not None
        ):
            now = datetime.now(MOSCOW_TZ)

            try:
                old_hour, old_minute = map(int, old_notify_time.split(":"))
            except ValueError:
                old_hour = old_minute = None

            if old_hour is not None:
                today_old_time = now.replace(
                    hour=old_hour,
                    minute=old_minute,
                    second=0,
                    microsecond=0,
                )

                # Ситуация из бага: время изменили ДО наступления старого времени.
                if today_old_time > now:
                    delay = (today_old_time - now).total_seconds()

                    async def _send_today_practice_job(job_context: ContextTypes.DEFAULT_TYPE):
                        job = job_context.job
                        job_user_id = job.data["user_id"]
                        job_chat_id = job.data["chat_id"]
                        weekday = get_current_weekday()
                        await send_practice_to_user(job_context, job_user_id, job_chat_id, weekday)

                    context.job_queue.run_once(
                        _send_today_practice_job,
                        when=timedelta(seconds=delay),
                        data={"user_id": user_id, "chat_id": chat_id},
                        name=f"today_practice_{user_id}_{old_notify_time.replace(':', '')}",
                    )
    except Exception as e:
        print(f"=== DEBUG: Ошибка при планировании сегодняшней практики по старому времени для user_id={user_id}: {e} ===")

    # Сообщение для изменения времени
    success_text = (
        f"Время успешно изменено ✔️\n"
        f"Начиная с завтрашнего дня жди меня в это время!"
    )
    
    # Отправляем краткое сообщение об изменении времени
    await update.message.reply_text(success_text)
