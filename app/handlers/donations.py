"""Handler for donations information."""

from telegram import Update
from telegram.ext import ContextTypes


async def handle_donations_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Донаты'.
    
    Показывает информацию о поддержке проекта.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Отвечаем на callback query если это inline кнопка
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Получаем chat_id
    chat_id = update.effective_chat.id
    
    # Информация о донатах
    donations_text = (
        "**Поддержка проекта**\n\n"
        "Если YogaDailyBot помогает тебе в практике йоги, ты можешь поддержать его развитие!\n\n"
        "💳 **Способы поддержки:**\n"
        "• Карта: `5536 9138 1234 5678`\n"
        "• ЮМоней: `410011123456789`\n"
        "• Патреон: patreon.com/yogadailybot\n"
        "• Крипто: BTC `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa`\n\n"
        " **Любая поддержка важна!**\n"
        "Нам одинаково ценны и 5 рублей, и 500 – всё идёт на благо проекта и расширения библиотеки практик.\n\n"
        "Спасибо!"
    )
    
    # Отправляем сообщение
    await context.bot.send_message(
        chat_id=chat_id,
        text=donations_text,
        parse_mode='Markdown'
    )
