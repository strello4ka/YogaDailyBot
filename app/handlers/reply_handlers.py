"""Reply keyboard handlers for YogaDailyBot.
Обработчики для Reply-клавиатуры с основными функциями бота.
"""

from telegram import Update
from telegram.ext import ContextTypes
from app.keyboards import get_main_reply_keyboard


async def handle_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок Reply-клавиатуры.
    
    Обрабатывает текстовые сообщения, соответствующие кнопкам Reply-клавиатуры:
    - "Изменить время" - переадресация к обработчику изменения времени
    - "Предложить практику" - переадресация к обработчику предложения практик
    - "Помощь" - переадресация к обработчику помощи
    - "Начать сначала" - переадресация к обработчику сброса
    - "Донаты" - переадресация к обработчику донатов
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Получаем текст сообщения
    message_text = update.message.text
    
    # Вызываем обработчики напрямую без имитации callback_query
    if message_text == "Изменить время":
        from app.handlers.set_time import handle_set_time_callback
        await handle_set_time_callback(update, context)
        
    elif message_text == "Предложить практику":
        from app.handlers.suggest_practice import handle_suggest_practice_callback
        await handle_suggest_practice_callback(update, context)
        
    elif message_text == "Помощь":
        from app.handlers.help import handle_help_callback
        await handle_help_callback(update, context)
        
    elif message_text == "Начать сначала":
        from app.handlers.restart import handle_restart_callback
        await handle_restart_callback(update, context)
        
    elif message_text == "Донаты":
        from app.handlers.donations import handle_donations_callback
        await handle_donations_callback(update, context)
        
    else:
        # Если текст не соответствует ни одной кнопке Reply-клавиатуры,
        # не обрабатываем (оставляем для других обработчиков)
        return



