"""Entrypoint for YogaDailyBot.
Main application file that initializes the bot and registers all handlers.
"""

import asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, PreCheckoutQueryHandler, filters, ContextTypes
from telegram import Update

from .config import BOT_TOKEN
from .onboarding import (
    start_command,
    want_start_callback,
    handle_time_input,
    cancel_time_callback
)
from .handlers.set_time import handle_time_change_input
from .handlers.reply_handlers import handle_reply_button
from .handlers.suggest_practice import handle_practice_suggestion_input
from .handlers.donations import (
    handle_donations_callback,
    handle_donate_card_callback,
    handle_donate_stars_callback,
    handle_stars_amount_callback,
    handle_pre_checkout_query,
    handle_successful_payment
)
from .schedule.scheduler import schedule_daily_practices, send_test_practice


async def handle_text_input(update: Update, context):
    """Универсальный обработчик текстовых сообщений.
    
    Определяет, какой обработчик вызвать на основе состояния пользователя.
    """
    print(f"=== DEBUG: handle_text_input вызвана ===")
    print(f"Message text: '{update.message.text}'")
    print(f"User data: {context.user_data}")
    
    # Проверяем состояние ожидания предложения практики
    if context.user_data.get('waiting_for_practice_suggestion'):
        print("=== DEBUG: Переадресация на handle_practice_suggestion_input ===")
        await handle_practice_suggestion_input(update, context)
        return
    
    # Проверяем состояние ожидания ввода времени
    if context.user_data.get('waiting_for_time'):
        # Проверяем, это изменение времени или онбординг
        if context.user_data.get('is_time_change'):
            print("=== DEBUG: Переадресация на handle_time_change_input (изменение времени) ===")
            await handle_time_change_input(update, context)
        else:
            print("=== DEBUG: Переадресация на handle_time_input (онбординг) ===")
            await handle_time_input(update, context)
        return
    
    print("=== DEBUG: Никакое состояние не установлено, сообщение игнорируется ===")
    # Если никакое состояние не установлено, сбрасываем возможные "зависшие" состояния
    # и игнорируем сообщение (это может быть обычное сообщение пользователя)
    context.user_data.pop('waiting_for_practice_suggestion', None)
    context.user_data.pop('waiting_for_time', None)

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


async def help_command(update: Update, context):
    """Команда для получения справки по боту."""
    # Очищаем состояние ожидания предложения практики, если оно было установлено
    # Это нужно, чтобы пользователь мог взаимодействовать с другими функциями бота
    context.user_data.pop('waiting_for_practice_suggestion', None)
    context.user_data.pop('waiting_for_time', None)
    
    chat_id = update.effective_chat.id
    
    # Справка по использованию бота
    help_text = (
        "*Мой проект только зарождается, поэтому так важен любой фитбек* 🧡\n\n" 
        "Если хочешь сообщить об ошибке, предложить идею или просто общаться с другими пользователями бота, то заходи в [Чатик бота](https://t.me/+YYkM0HgbFqVmMTZi) или пиши @strello4ka.\n\n" 
        "Благодаря тебе YogaDailyBot станет лучше!"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')
    logger.info(f"Отправлена справка пользователю {update.effective_user.id}")


def main():
    """Основная функция запуска бота."""
    # Создаем приложение с JobQueue
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_practice_command))
    application.add_handler(CommandHandler("myid", myid_command))
    
    # Регистрируем обработчики callback-запросов (только для онбординга)
    application.add_handler(CallbackQueryHandler(want_start_callback, pattern="^want_start$"))
    application.add_handler(CallbackQueryHandler(cancel_time_callback, pattern="^cancel_time$"))
    
    # Регистрируем обработчики для донатов
    application.add_handler(CallbackQueryHandler(handle_donate_card_callback, pattern="^donate_card$"))
    application.add_handler(CallbackQueryHandler(handle_donate_stars_callback, pattern="^donate_stars$"))
    
    # Регистрируем обработчики для выбора количества звезд
    application.add_handler(CallbackQueryHandler(handle_stars_amount_callback, pattern="^stars_"))
    
    # Регистрируем обработчики для платежей
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    
    # Регистрируем обработчик Reply-кнопок (с высоким приоритетом)
    reply_buttons = ["Изменить время", "Предложить практику", "Советы", "Начать сначала", "Донаты"]
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(f"^({'|'.join(reply_buttons)})$"),
        handle_reply_button
    ))
    
    # Регистрируем обработчик текстовых сообщений для ввода времени и предложений практик
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Планируем ежедневную отправку практик
    schedule_daily_practices(application)
    
    # Запускаем бота
    logger.info("Запускаем YogaDailyBot с JobQueue...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
