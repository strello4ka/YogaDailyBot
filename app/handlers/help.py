"""/help handler."""

from telegram import Update
from telegram.ext import ContextTypes


async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Помощь'.
    
    Показывает справку по использованию бота.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Отвечаем на callback query если это inline кнопка
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Получаем chat_id
    chat_id = update.effective_chat.id
    
    # Справочное сообщение
    help_text = (
        "❓ **Помощь по YogaDailyBot**\n\n"
        "🧘‍♀️ **О боте:**\n"
        "YogaDailyBot – это твой персональный помощник для ежедневных йога-практик. Каждый день в выбранное время я пришлю тебе короткую эффективную йога-практику.\n\n"
        "🕰️ **Основные функции:**\n"
        "• **Изменить время** – настрой время получения рассылки\n"
        "• **Предложить практику** – поделись своей любимой практикой\n"
        "• **Начать сначала** – сбрось счётчик дней и пройди онбординг заново\n"
        "• **Донаты** – поддержи развитие проекта\n\n"
        "💬 **Команды:**\n"
        "• `/start` – запуск бота и онбординг\n"
        "• `/help` – показать эту справку\n"
        "• `/test` – получить тестовую практику\n"
        "• `/myid` – узнать свой ID\n\n"
        "🔄 **Клавиатуры:**\n"
        "Используй кнопки ниже для быстрого доступа к функциям бота или inline-кнопки в сообщениях.\n\n"
        "🔗 **Полезно знать:**\n"
        "• Все времена указываются по московскому времени\n"
        "• Практики размещены на YouTube\n"
        "• Для просмотра в России потребуется VPN\n\n"
        "💬 **Связь:** @strello4ka"
    )
    
    # Отправляем сообщение
    await context.bot.send_message(
        chat_id=chat_id,
        text=help_text,
        parse_mode='Markdown'
    )
