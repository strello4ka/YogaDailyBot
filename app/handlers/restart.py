"""Handler for resetting user settings and onboarding again."""

from telegram import Update
from telegram.ext import ContextTypes


async def handle_restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Начать сначала'.
    
    Сбрасывает счетчик дней пользователя и запускает онбординг заново.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Отвечаем на callback query если это inline кнопка
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Получаем данные пользователя
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Сбрасываем счетчик дней пользователя
    from data.db import reset_user_days
    reset_success = reset_user_days(user_id)
    
    if reset_success:
        # Отправляем подтверждение
        await context.bot.send_message(
            chat_id=chat_id,
            text="Счетчик дней сброшен! Теперь начнем сначала."
        )
        
        # Запускаем онбординг заново
        from app.onboarding import start_command
        await start_command(update, context)
    else:
        # Отправляем сообщение об ошибке
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Ошибка сброса счетчика дней. Попробуй еще раз."
        )
