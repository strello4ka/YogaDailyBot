"""Handlers for selecting and saving preferred delivery time."""

from telegram import Update
from telegram.ext import ContextTypes


async def handle_set_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Изменить время'.
    
    Запускает процесс изменения времени доставки уведомлений.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Отвечаем на callback query если это inline кнопка
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Устанавливаем состояние ожидания ввода времени
    context.user_data['waiting_for_time'] = True
    
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
