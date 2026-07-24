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
from app.keyboards import get_practice_action_keyboard
from data.db import (
    get_users_pending_for_today,
    get_yoga_practice_by_weekday_order,
    get_yoga_practice_by_challenge_order,
    get_user_challenge_start_id,
    increment_total_practices,
    get_total_practices,
    get_program_position,
    increment_program_position,
    get_user_challenge_day,
    increment_challenge_day,
    set_user_challenge_day,
    set_last_practice_message_id,
    log_practice_sent,
    get_current_weekday,
    get_bonus_practices_by_parent,
    is_user_favorite,
)
from app.challenge.cohort import get_cohort_challenge_day, is_cohort_configured
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
        
        # Получаем всех пользователей, которые должны получить практику сегодня:
        # их время уведомлений уже наступило (notify_time <= current_time),
        # и в логах practice_logs за сегодня ещё нет записи.
        users = get_users_pending_for_today(current_time)
        
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
    
    Если у пользователя включён режим челленджа — практика по challenge_start_id и дню потока.
    Иначе — практика по дню недели и счётчику дней.
    
    Args:
        context: Контекст бота
        user_id: ID пользователя
        chat_id: ID чата
        weekday: день недели (используется только в обычном режиме)
    """
    try:
        # Снимаем «Я сделал!» только если предыдущая практика не за сегодня
        from app.handlers.done import strip_previous_day_done_button

        await strip_previous_day_done_button(context.bot, chat_id, user_id)

        # Вычисляем плановые счётчики, но подтверждаем их только после успешной отправки.
        # Это защищает от скачков прогресса при сетевых таймаутах Telegram API.
        program_position = get_program_position(user_id)
        next_position = program_position + 1
        total_practices = get_total_practices(user_id) + 1
        if is_cohort_configured():
            challenge_day = get_cohort_challenge_day()
            if challenge_day < 1 or challenge_day > 28:
                logger.info(
                    "Пропуск челлендж-рассылки user=%s: день потока=%s",
                    user_id,
                    challenge_day,
                )
                return
        else:
            challenge_day = get_user_challenge_day(user_id) + 1

        # Daily выбирается по program_position; Challenge — по стартовому id потока и дню.
        start_id = get_user_challenge_start_id(user_id)
        if start_id is not None:
            practice = get_yoga_practice_by_challenge_order(start_id, challenge_day)
            is_challenge = True
        else:
            practice = get_yoga_practice_by_weekday_order(weekday, next_position)
            is_challenge = False
        if not practice:
            if is_challenge:
                logger.error(f"Не найдена практика челленджа для пользователя {user_id}, день {challenge_day}")
            else:
                logger.error(f"Не найдена практика для дня недели {weekday}, день {next_position}")
            return

        # Распаковываем данные практики
        (practice_id, title, video_url, time_practices, channel_name,
         description, my_description, intensity, practice_weekday, created_at, updated_at) = practice

        title = f"{challenge_day} день челленджа" if is_challenge else "Практика дня"
        message_text = format_practice_message(title, my_description, time_practices, intensity, channel_name, video_url)

        # Отправляем сообщение с кнопками избранного и «✅ Я сделал!»
        done_keyboard = get_practice_action_keyboard(
            practice_id, is_user_favorite(user_id, practice_id)
        )

        # Отправляем сообщение с кнопкой
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='Markdown',
            disable_web_page_preview=False,
            reply_markup=done_keyboard
        )
        set_last_practice_message_id(user_id, message.message_id, practice_id)

        # Подтверждаем прогресс только после успешной отправки пользователю.
        if is_challenge:
            if is_cohort_configured():
                set_user_challenge_day(user_id, challenge_day)
            else:
                increment_challenge_day(user_id)
        else:
            increment_program_position(user_id)
        increment_total_practices(user_id)

        # Логируем отправку основной практики
        log_id = log_practice_sent(
            user_id,
            practice_id,
            total_practices,
            chat_id=chat_id,
            message_id=message.message_id,
        )
        if log_id:
            from app.handlers.done import schedule_done_reminders

            await schedule_done_reminders(context, chat_id, user_id, log_id)

        logger.info(f"Практика {practice_id} отправлена пользователю {user_id}, всего практик {total_practices}")
        
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


def format_practice_message(title: str, my_description: str, time_practices: int,
                          intensity: str, channel_name: str, video_url: str) -> str:
    """Форматирует сообщение с практикой.
    
    Args:
        title: заголовок сообщения (например, «Практика дня» или «1 день челленджа»)
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
        f"*{title}*\n"
    ]
    
    if my_description:
        message_parts.append(f"{my_description}")
    else:
        # Если нет my_description, формируем базовое описание
        message_parts.append(f"Новая практика ждет тебя!")
    
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

        from app.handlers.done import strip_previous_day_done_button

        await strip_previous_day_done_button(context.bot, chat_id, user_id)

        program_position = get_program_position(user_id)
        next_position = program_position + 1
        total_practices = get_total_practices(user_id) + 1

        current_weekday = get_current_weekday()
        practice = get_yoga_practice_by_weekday_order(current_weekday, next_position)

        if not practice:
            logger.error(f"Не найдена практика для дня недели {current_weekday}, день {next_position}")
            await context.bot.send_message(chat_id, "❌ Практика не найдена для текущего дня недели")
            return

        (practice_id, title, video_url, time_practices, channel_name,
         description, my_description, intensity, practice_weekday, created_at, updated_at) = practice

        message_text = format_practice_message("Практика дня", my_description, time_practices, intensity, channel_name, video_url)
        done_keyboard = get_practice_action_keyboard(
            practice_id, is_user_favorite(user_id, practice_id)
        )

        message = await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode='Markdown',
            disable_web_page_preview=False,
            reply_markup=done_keyboard
        )
        set_last_practice_message_id(user_id, message.message_id, practice_id)

        increment_program_position(user_id)
        increment_total_practices(user_id)

        log_id = log_practice_sent(
            user_id,
            practice_id,
            total_practices,
            chat_id=chat_id,
            message_id=message.message_id,
        )
        if log_id:
            from app.handlers.done import schedule_done_reminders

            await schedule_done_reminders(context, chat_id, user_id, log_id)
        logger.info(f"Тестовая практика {practice_id} отправлена пользователю {user_id}, всего практик {total_practices}")
        
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
