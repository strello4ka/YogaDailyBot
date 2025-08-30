"""Handler for accepting user-suggested practice links."""

from telegram import Update
from telegram.ext import ContextTypes


async def handle_suggest_practice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Предложить практику'.
    
    Показывает инструкцию по отправке предложений практик.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Отвечаем на callback query если это inline кнопка
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Получаем chat_id
    chat_id = update.effective_chat.id
    
    # Сообщение о предложении практик
    suggest_text = (
        "🧘‍♀️ **Предложить практику**\n\n"
        "Нашел классную йога-практику на YouTube? 🎉\n\n"
        "Поделись ссылкой, и я с радостью рассмотрю её для добавления в рассылку!\n\n"
        "**Как предложить:**\n"
        "• Отправь ссылку на YouTube-видео\n"
        "• Можно добавить комментарий, почему эта практика классная\n"
        "• Напиши @strello4ka личным сообщением\n\n"
        "🔍 **Критерии отбора:**\n"
        "• Продолжительность: 10-25 минут\n"
        "• Подходит для начинающих/среднего уровня\n"
        "• Качественное видео и звук\n"
        "• На русском языке (предпочтительно)\n\n"
        "💬 **Контакт:** @strello4ka"
    )
    
    # Отправляем сообщение
    await context.bot.send_message(
        chat_id=chat_id,
        text=suggest_text,
        parse_mode='Markdown'
    )
