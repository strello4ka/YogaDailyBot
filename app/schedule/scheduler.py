"""Scheduler module for YogaDailyBot.
Handles daily practice sending and scheduling.
"""

import sys
import os
# Добавляем корневую директорию проекта в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from datetime import datetime, time
from telegram.ext import ContextTypes
from data.db import (
    get_users_by_time, 
    get_yoga_practice_by_weekday_order,
    increment_user_days,
    get_user_days,
    log_practice_sent,
    get_current_weekday,
    get_user_time,
    get_newbie_practice_by_number,
    get_max_newbie_practice_number
)

logger = logging.getLogger(__name__)


async def send_daily_practice(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет ежедневную практику всем пользователям в указанное время.
    
    Args:
        context: Контекст бота
    """
    try:
        # Получаем текущее время в формате HH:MM
        current_time = datetime.now().strftime("%H:%M")
        
        # Получаем всех пользователей, которые должны получить практику в это время
        users = get_users_by_time(current_time)
        
        if not users:
            logger.info(f"Нет пользователей для отправки практики в {current_time}")
            return
        
        # Получаем текущий день недели
        current_weekday = get_current_weekday()
        
        logger.info(f"Отправляем практики {len(users)} пользователям в {current_time}, день недели: {current_weekday}")
        
        # Отправляем практику каждому пользователю
        for user_id, chat_id in users:
            await send_practice_to_user(context, user_id, chat_id, current_weekday)
            
    except Exception as e:
        logger.error(f"Ошибка отправки ежедневных практик: {e}")


async def send_practice_to_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, weekday: int):
    """Отправляет практику конкретному пользователю.
    
    Args:
        context: Контекст бота
        user_id: ID пользователя
        chat_id: ID чата
        weekday: день недели
    """
    try:
        # Получаем данные пользователя
        user_data = get_user_time(user_id)
        if not user_data or not user_data[0]:  # Проверяем chat_id
            logger.error(f"Пользователь {user_id} не найден")
            return
        
        chat_id, notify_time, user_name, user_phone, user_days, onboarding_weekday = user_data
        
        # Увеличиваем счетчик дней
        increment_user_days(user_id)
        new_day_number = user_days + 1
        
        # Определяем, новичок ли пользователь (первые 28 дней)
        if new_day_number <= 28:
            await send_newbie_practice(context, user_id, chat_id, onboarding_weekday, new_day_number)
        else:
            await send_regular_practice(context, user_id, chat_id, weekday, new_day_number)
        
    except Exception as e:
        logger.error(f"Ошибка отправки практики пользователю {user_id}: {e}")


async def send_newbie_practice(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, onboarding_weekday: int, day_number: int):
    """Отправляет практику новичку из фиксированного набора.
    
    Args:
        context: Контекст бота
        user_id: ID пользователя
        chat_id: ID чата
        onboarding_weekday: день недели регистрации
        day_number: номер дня пользователя
    """
    try:
        # Вычисляем номер практики для новичка
        # Если пользователь зарегистрировался в воскресенье (7), то первая практика под номером 1
        # Если в понедельник (1), то первая практика под номером 2, и т.д.
        if onboarding_weekday is None:
            onboarding_weekday = get_current_weekday()
        
        # Вычисляем номер практики на основе дня регистрации
        # Воскресенье (7) → Практика #1, Понедельник (1) → Практика #2, и т.д.
        practice_number = (onboarding_weekday % 7) + 1
        
        # Получаем практики для этого номера
        practices = get_newbie_practice_by_number(practice_number)
        
        if not practices:
            logger.error(f"Не найдены практики новичков для номера {practice_number}")
            # Если не найдены практики новичков, переключаемся на обычные практики
            await send_regular_practice(context, user_id, chat_id, get_current_weekday(), day_number)
            return
        
        # Отправляем все практики для данного номера с интервалом 1 минута
        for i, practice in enumerate(practices):
            (practice_id, title, video_url, duration_minutes, channel_name, 
             description, number_practices, created_at, updated_at) = practice
            
            # Формируем сообщение для новичка
            message_text = format_newbie_practice_message(day_number, description, duration_minutes, channel_name, video_url)
            
            # Отправляем сообщение с задержкой для множественных практик
            if i > 0:
                await asyncio.sleep(60)  # 1 минута задержки между практиками
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            
            # Логируем отправку
            log_practice_sent(user_id, practice_id, day_number)
            
            logger.info(f"Практика новичка {practice_id} отправлена пользователю {user_id}, день {day_number}")
        
        # Проверяем, нужно ли перейти к следующей неделе
        max_practice_number = get_max_newbie_practice_number()
        if practice_number >= max_practice_number and user_week < 4:
            # Переходим к следующей неделе
            new_week = user_week + 1
            update_user_week(user_id, new_week)
            logger.info(f"Пользователь {user_id} переведен на неделю {new_week}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки практики новичка пользователю {user_id}: {e}")


async def send_regular_practice(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, weekday: int, day_number: int):
    """Отправляет обычную практику пользователю.
    
    Args:
        context: Контекст бота
        user_id: ID пользователя
        chat_id: ID чата
        weekday: день недели
        day_number: номер дня пользователя
    """
    try:
        # Получаем практику для текущего дня недели по порядку
        practice = get_yoga_practice_by_weekday_order(weekday, day_number)
        
        if not practice:
            logger.error(f"Не найдена практика для дня недели {weekday}, день {day_number}")
            return
        
        # Распаковываем данные практики
        (practice_id, title, video_url, time_practices, channel_name, 
         description, my_description, intensity, practice_weekday, created_at, updated_at) = practice
        
        # Формируем сообщение
        message_text = format_practice_message(day_number, my_description, time_practices, intensity, channel_name, video_url)
        
        # Отправляем сообщение
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='Markdown',
            disable_web_page_preview=False  # Включаем превью видео
        )
        
        # Логируем отправку
        log_practice_sent(user_id, practice_id, day_number)
        
        logger.info(f"Практика {practice_id} отправлена пользователю {user_id}, день {day_number}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки обычной практики пользователю {user_id}: {e}")


def format_practice_message(day_number: int, my_description: str, time_practices: int, 
                          intensity: str, channel_name: str, video_url: str) -> str:
    """Форматирует сообщение с практикой.
    
    Args:
        day_number: номер дня пользователя
        my_description: описание практики
        time_practices: длительность в минутах
        intensity: интенсивность
        channel_name: название канала
        video_url: ссылка на видео
        
    Returns:
        str: Отформатированное сообщение
    """
    # Формируем сообщение согласно требованиям
    message_parts = [
        f"{day_number} день\n"
    ]
    
    if my_description:
        message_parts.append(f"{my_description}")
    else:
        # Если нет my_description, формируем базовое описание
        message_parts.append(f"Сегодня у нас практика от канала {channel_name}")
    
    message_parts.append(f"\n🌀 {time_practices} минут")
    
    if intensity:
        message_parts.append(f"🌀 {intensity}")
    
    message_parts.append(f"🌀 {channel_name}")
    
    message_parts.append(f"\n▶️ [Youtube]({video_url})")
    
    return "\n".join(message_parts)


def format_newbie_practice_message(day_number: int, description: str, duration_minutes: int, 
                                 channel_name: str, video_url: str) -> str:
    """Форматирует сообщение с практикой для новичков.
    
    Args:
        day_number: номер дня пользователя
        description: описание практики
        duration_minutes: длительность в минутах
        channel_name: название канала
        video_url: ссылка на видео
        
    Returns:
        str: Отформатированное сообщение
    """
    # Формируем сообщение для новичков
    message_parts = [
        f"{day_number} день (программа для новичков)\n"
    ]
    
    if description:
        message_parts.append(f"{description}")
    else:
        # Если нет описания, формируем базовое описание
        message_parts.append(f"Сегодня у нас практика от канала {channel_name}")
    
    message_parts.append(f"\n🌀 {duration_minutes} минут")
    message_parts.append(f"🌀 {channel_name}")
    
    message_parts.append(f"\n▶️ [Youtube]({video_url})")
    
    return "\n".join(message_parts)


def schedule_daily_practices(application):
    """Планирует ежедневную отправку практик.
    
    Args:
        application: Экземпляр приложения бота
    """
    try:
        job_queue = application.job_queue
        
        if not job_queue:
            logger.error("JobQueue недоступен")
            return
        
        # Планируем отправку практик каждую минуту для проверки времени
        # Это не очень эффективно, но простое решение для MVP
        job_queue.run_repeating(
            send_daily_practice,
            interval=60,  # каждую минуту
            first=1,  # через 1 секунду после запуска
            name="daily_practice_sender"
        )
        
        logger.info("Ежедневная отправка практик запланирована")
        
    except Exception as e:
        logger.error(f"Ошибка планирования ежедневных практик: {e}")


async def send_test_practice(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int):
    """Отправляет тестовую практику пользователю (для отладки).
    
    Args:
        context: Контекст бота
        user_id: ID пользователя
        chat_id: ID чата
    """
    try:
        logger.info(f"Отправка тестовой практики пользователю {user_id}")
        
        # Получаем текущий день недели
        current_weekday = get_current_weekday()
        
        # Используем основную функцию отправки практики
        await send_practice_to_user(context, user_id, chat_id, current_weekday)
        
    except Exception as e:
        logger.error(f"Ошибка отправки тестовой практики пользователю {user_id}: {e}")
        # Отправляем сообщение об ошибке пользователю
        try:
            await context.bot.send_message(chat_id, f"❌ Ошибка отправки практики: {str(e)}")
        except:
            pass
