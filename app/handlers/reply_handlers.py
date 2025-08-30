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
    
    # Импортируем нужные обработчики только при необходимости
    if message_text == "Изменить время":
        from app.handlers.set_time import handle_set_time_callback
        # Создаем имитацию callback query для совместимости с существующим обработчиком
        fake_query = type('obj', (object,), {
            'answer': lambda self: None,
            'data': 'change_time'
        })()
        
        # Создаем имитацию update с callback_query
        fake_update = type('obj', (object,), {
            'callback_query': fake_query,
            'effective_user': update.effective_user,
            'effective_chat': update.effective_chat
        })()
        
        await handle_set_time_callback(fake_update, context)
        
    elif message_text == "Предложить практику":
        from app.handlers.suggest_practice import handle_suggest_practice_callback
        # Аналогично создаем имитацию для существующего обработчика
        fake_query = type('obj', (object,), {
            'answer': lambda self: None,
            'data': 'suggest_practice'
        })()
        
        fake_update = type('obj', (object,), {
            'callback_query': fake_query,
            'effective_user': update.effective_user,
            'effective_chat': update.effective_chat
        })()
        
        await handle_suggest_practice_callback(fake_update, context)
        
    elif message_text == "Помощь":
        from app.handlers.help import handle_help_callback
        # Аналогично создаем имитацию для существующего обработчика
        fake_query = type('obj', (object,), {
            'answer': lambda self: None,
            'data': 'help'
        })()
        
        fake_update = type('obj', (object,), {
            'callback_query': fake_query,
            'effective_user': update.effective_user,
            'effective_chat': update.effective_chat
        })()
        
        await handle_help_callback(fake_update, context)
        
    elif message_text == "Начать сначала":
        from app.onboarding import reset_user_callback
        # Аналогично создаем имитацию для существующего обработчика
        fake_query = type('obj', (object,), {
            'answer': lambda self: None,
            'data': 'reset'
        })()
        
        fake_update = type('obj', (object,), {
            'callback_query': fake_query,
            'effective_user': update.effective_user,
            'effective_chat': update.effective_chat
        })()
        
        await reset_user_callback(fake_update, context)
        
    elif message_text == "Донаты":
        from app.handlers.donations import handle_donations_callback
        # Аналогично создаем имитацию для существующего обработчика
        fake_query = type('obj', (object,), {
            'answer': lambda self: None,
            'data': 'donations'
        })()
        
        fake_update = type('obj', (object,), {
            'callback_query': fake_query,
            'effective_user': update.effective_user,
            'effective_chat': update.effective_chat
        })()
        
        await handle_donations_callback(fake_update, context)
        
    else:
        # Если текст не соответствует ни одной кнопке Reply-клавиатуры,
        # не обрабатываем (оставляем для других обработчиков)
        return


async def show_main_reply_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает главную Reply-клавиатуру пользователю.
    
    Отправляет сообщение с Reply-клавиатурой и описанием функций.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    menu_text = (
        "📱 **Главное меню**\n\n"
        "Используй кнопки ниже для быстрого доступа к функциям бота:"
    )
    
    await update.message.reply_text(
        menu_text,
        reply_markup=get_main_reply_keyboard(),
        parse_mode='Markdown'
    )
