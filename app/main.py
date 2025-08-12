"""Entrypoint for YogaDailyBot.
Main application file that initializes the bot and registers all handlers.
"""

import asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update

from app.config import BOT_TOKEN
from app.onboarding import (
    start_command,
    want_start_callback,
    handle_time_input,
    cancel_time_callback
)

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


def main():
    """Основная функция запуска бота."""
    # Создаем приложение с JobQueue
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    
    # Регистрируем обработчики callback-запросов (кнопки)
    application.add_handler(CallbackQueryHandler(want_start_callback, pattern="^want_start$"))
    application.add_handler(CallbackQueryHandler(cancel_time_callback, pattern="^cancel_time$"))
    
    # Регистрируем обработчик текстовых сообщений для ввода времени
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Запускаем YogaDailyBot с JobQueue...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
