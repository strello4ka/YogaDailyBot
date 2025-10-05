"""Handlers for selecting and saving preferred delivery time."""

import re
from telegram import Update
from telegram.ext import ContextTypes


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
        "⏰ **Изменение времени доставки**\n\n"
        "Введи новое время в формате ЧЧ:ММ (например, 09:30)\n\n"
        "*Время указывается по московскому часовому поясу*"
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
            f"❌ {result}\n\n"
            "Попробуй еще раз в формате ЧЧ:ММ"
        )
        return
    
    # Время валидно, сохраняем его
    selected_time = result
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Убираем состояние ожидания
    context.user_data.pop('waiting_for_time', None)
    context.user_data.pop('is_time_change', None)
    
    # Сохраняем время в базу данных (НЕ изменяем день недели регистрации)
    from data.db import save_user_time
    user_name = update.effective_user.first_name
    save_success = save_user_time(user_id, chat_id, selected_time, user_name, onboarding_weekday=None)
    
    if not save_success:
        print(f"Ошибка сохранения времени пользователя {user_id} в БД")
    
    # Сообщение для изменения времени
    success_text = (
        f"Время успешно изменено.\n"
        f"Начиная с завтрашнего дня жди меня в это время"
    )
    
    # Отправляем краткое сообщение об изменении времени
    await update.message.reply_text(success_text)
