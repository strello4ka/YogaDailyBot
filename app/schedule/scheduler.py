"""Scheduler module for YogaDailyBot.
Handles daily practice sending and scheduling.
"""

import sys
import os
# Добавляем корневую директорию проекта в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo  # Используем таймзону, чтобы сравнивать время корректно
from telegram.ext import ContextTypes
from data.db import (
    get_users_by_time, 
    get_yoga_practice_by_weekday_order,
    increment_user_days,
    get_user_days,
    log_practice_sent,
    get_current_weekday,
    get_bonus_practices_by_parent
)
from app.config import DEFAULT_TZ  # Подтягиваем базовую таймзону проекта

logger = logging.getLogger(__name__)

# Создаём объект таймзоны один раз, чтобы переиспользовать его в дальнейших расчётах
MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)


async def send_daily_practice(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет ежедневную практику всем пользователям в указанное время.
    
    Args:
        context: Контекст бота
    """
    try:
        # Получаем текущее время в базовой таймзоне, чтобы сравнение с notify_time было честным
        current_time = datetime.now(MOSCOW_TZ).strftime("%H:%M")
        
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
        # Получаем количество дней пользователя
        user_days = get_user_days(user_id)
        
        # Увеличиваем счетчик дней
        increment_user_days(user_id)
        new_day_number = user_days + 1
        
        # Получаем практику для текущего дня недели по порядку
        practice = get_yoga_practice_by_weekday_order(weekday, new_day_number)
        
        if not practice:
            logger.error(f"Не найдена практика для дня недели {weekday}, день {new_day_number}")
            return
        
        # Распаковываем данные практики
        (practice_id, title, video_url, time_practices, channel_name, 
         description, my_description, intensity, practice_weekday, created_at, updated_at) = practice
        
        # Формируем сообщение
        message_text = format_practice_message(new_day_number, my_description, time_practices, intensity, channel_name, video_url)
        
        # Отправляем сообщение
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='Markdown',
            disable_web_page_preview=False  # Включаем превью видео
        )
        
        # Логируем отправку основной практики
        log_practice_sent(user_id, practice_id, new_day_number)
        
        logger.info(f"Практика {practice_id} отправлена пользователю {user_id}, день {new_day_number}")
        
        # Получаем бонусные практики, если они есть
        bonus_practices = get_bonus_practices_by_parent(practice_id)
        
        for bonus in bonus_practices:
            # Берем только нужные колонки, чтобы не плодить неиспользуемые переменные
            bonus_id = bonus[0]
            bonus_url = bonus[3]
            bonus_my_description = bonus[7]
            
            # Формируем бонусное сообщение
            bonus_message = format_bonus_practice_message(bonus_my_description, bonus_url)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=bonus_message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            
            logger.info(f"Бонусная практика {bonus_id} отправлена пользователю {user_id} вместе с {practice_id}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки практики пользователю {user_id}: {e}")


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
        f"*{day_number} день*\n"
    ]
    
    if my_description:
        message_parts.append(f"{my_description}")
    else:
        # Если нет my_description, формируем базовое описание
        message_parts.append(f"Новая праткика ждет тебя!")
    
    message_parts.append(f"\n🌀 *время:* {time_practices} мин")
    
    if intensity:
        message_parts.append(f"🌀 *интенсивность:* {intensity}")
    
    message_parts.append(f"🌀 *канал:* {channel_name}")
    
    message_parts.append(f"\n▶️ [Youtube]({video_url})")
    
    return "\n".join(message_parts)


def format_bonus_practice_message(my_description: str, video_url: str) -> str:
    """Форматирует сообщение с бонусной практикой.
    
    Args:
        my_description: описание бонусной практики
        video_url: ссылка на бонусное видео
        
    Returns:
        str: сообщение в требуемом формате
    """
    # Формат сообщения
    title_line = "*Бонус недели*"
    
    description_text = my_description.strip() if my_description else "Пробуй новое, ищи свое"
    
    return "\n".join([
        title_line,
        "",
        description_text,
        "",
        f"▶️ [Youtube]({video_url})"
    ])


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
        
        # Получаем количество дней пользователя
        user_days = get_user_days(user_id)
        
        # Увеличиваем счетчик дней
        increment_user_days(user_id)
        new_day_number = user_days + 1
        
        # Получаем текущий день недели
        current_weekday = get_current_weekday()
        
        # Получаем практику для текущего дня недели по порядку
        practice = get_yoga_practice_by_weekday_order(current_weekday, new_day_number)
        
        if not practice:
            logger.error(f"Не найдена практика для дня недели {current_weekday}, день {new_day_number}")
            await context.bot.send_message(chat_id, "❌ Практика не найдена для текущего дня недели")
            return
        
        # Распаковываем данные практики
        (practice_id, title, video_url, time_practices, channel_name, 
         description, my_description, intensity, practice_weekday, created_at, updated_at) = practice
        
        # Формируем сообщение
        message_text = format_practice_message(new_day_number, my_description, time_practices, intensity, channel_name, video_url)
        
        # Отправляем сообщение
        await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='Markdown',
            disable_web_page_preview=False  # Включаем превью видео
        )
        
        # Логируем отправку основной практики
        log_practice_sent(user_id, practice_id, new_day_number)
        
        logger.info(f"Тестовая практика {practice_id} отправлена пользователю {user_id}, день {new_day_number}")
        
        # Получаем бонусные практики, если они есть
        bonus_practices = get_bonus_practices_by_parent(practice_id)
        
        for bonus in bonus_practices:
            # Берем только нужные колонки, чтобы не плодить неиспользуемые переменные
            bonus_id = bonus[0]
            bonus_url = bonus[3]
            bonus_my_description = bonus[7]
            
            # Формируем бонусное сообщение
            bonus_message = format_bonus_practice_message(bonus_my_description, bonus_url)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=bonus_message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            
            logger.info(f"Бонусная практика {bonus_id} отправлена пользователю {user_id} вместе с {practice_id}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки тестовой практики пользователю {user_id}: {e}")
        # Отправляем сообщение об ошибке пользователю
        try:
            await context.bot.send_message(chat_id, f"❌ Ошибка отправки практики: {str(e)}")
        except:
            pass
