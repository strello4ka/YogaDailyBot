"""Entrypoint for YogaDailyBot.
Main application file that initializes the bot and registers all handlers.
"""

import sys
import os
# Добавляем корневую директорию проекта в путь
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update

from app.config import BOT_TOKEN
from app.onboarding import (
    start_command,
    want_start_callback,
    handle_time_input,
    cancel_time_callback,
    reset_user_callback
)
from app.scheduler import schedule_daily_practices, send_test_practice

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update, context):
    """Обработчик ошибок для логирования."""
    logger.error(f"Exception while handling an update: {context.error}")
    logger.error(f"Update: {update}")


async def test_practice_command(update: Update, context):
    """Команда для тестирования отправки практики."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    logger.info(f"Получена команда /test от пользователя {user_id}")
    
    try:
        await update.message.reply_text("Отправляю тестовую практику...")
        logger.info(f"Отправлено подтверждение пользователю {user_id}")
        
        await send_test_practice(context, user_id, chat_id)
        logger.info(f"Тестовая практика отправлена пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка в команде /test для пользователя {user_id}: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def myid_command(update: Update, context):
    """Команда для получения ID пользователя."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name
    
    message = f"👤 **Информация о пользователе:**\n\n"
    message += f"**Имя:** {user_name}\n"
    message += f"**User ID:** `{user_id}`\n"
    message += f"**Chat ID:** `{chat_id}`\n\n"
    message += f"💡 Используй эти ID для тестирования!"
    
    await update.message.reply_text(message, parse_mode='Markdown')
    logger.info(f"Отправлен ID пользователю {user_id}: user_id={user_id}, chat_id={chat_id}")


def main():
    """Основная функция запуска бота."""
    # Создаем приложение с JobQueue
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики callback-запросов (кнопки) ПЕРВЫМИ
    application.add_handler(CallbackQueryHandler(want_start_callback, pattern="^want_start$"))
    application.add_handler(CallbackQueryHandler(cancel_time_callback, pattern="^cancel_time$"))
    application.add_handler(CallbackQueryHandler(reset_user_callback, pattern="^reset$"))
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("test", test_practice_command))
    application.add_handler(CommandHandler("myid", myid_command))
    
    # Регистрируем обработчики callback-запросов (кнопки)
    application.add_handler(CallbackQueryHandler(want_start_callback, pattern="^want_start$"))
    application.add_handler(CallbackQueryHandler(cancel_time_callback, pattern="^cancel_time$"))
    application.add_handler(CallbackQueryHandler(reset_user_callback, pattern="^reset$"))
    
    # Регистрируем обработчик текстовых сообщений для ввода времени
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Планируем ежедневную отправку практик
    schedule_daily_practices(application)
    
    # Запускаем бота
    logger.info("Запускаем YogaDailyBot с JobQueue...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
