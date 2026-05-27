"""Handler for donations information."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    
    # Очищаем состояние ожидания предложения практики, если оно было установлено
    # Это нужно, чтобы пользователь мог взаимодействовать с другими функциями бота
    context.user_data.pop('waiting_for_practice_suggestion', None)
    
    # Получаем chat_id
    chat_id = update.effective_chat.id
    
    # Лаконичное сообщение о поддержке проекта
    donations_text = (
        "YogaDailyBot - бесплатный проект, но если он делает твою жизнь лучше, ты можешь поддержать его развитие!\n\n"
        "Любая поддержка ценна, от 1 рубля до бесконечности"
    )
    
    # Создаем клавиатуру с двумя кнопками
    keyboard = [
        [InlineKeyboardButton("💳 Перевести по номеру карты", callback_data="donate_card")],
        [InlineKeyboardButton("⭐️ Поддержать через Telegram Stars", callback_data="donate_stars")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение с кнопками
    await context.bot.send_message(
        chat_id=chat_id,
        text=donations_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def handle_donate_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Перевести по номеру карты'.
    
    Показывает номер карты и благодарность.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Отвечаем на callback query
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Получаем chat_id
    chat_id = update.effective_chat.id
    
    # Сообщение с номером карты и благодарностью
    card_text = (
        "💳 **Номер карты для перевода:**\n"
        "`2200701902278180`\n\n"
        "Спасибо за желание поддержать проект 🧡"
    )
    
    # Отправляем сообщение
    await context.bot.send_message(
        chat_id=chat_id,
        text=card_text,
        parse_mode='Markdown'
    )


async def handle_donate_stars_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Поддержать через Telegram Stars'.
    
    Показывает сообщение с призывом выбрать количество звезд и кнопки с вариантами.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Отвечаем на callback query
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Получаем chat_id
    chat_id = update.effective_chat.id
    
    # Сообщение с призывом выбрать количество звезд
    stars_text = (
        "*Поддержка через Telegram Stars* ⭐️\n\n"
        "Выбери количество звезд для поддержки проекта:\n\n"
        "Telegram Stars — это виртуальная валюта Telegram, "
        "которую можно купить в приложении."
    )
    
    # Создаем клавиатуру с вариантами количества звезд
    keyboard = [
        [InlineKeyboardButton("1 ⭐️", callback_data="stars_1")],
        [InlineKeyboardButton("5 ⭐️", callback_data="stars_5")],
        [InlineKeyboardButton("10 ⭐️", callback_data="stars_10")],
        [InlineKeyboardButton("50 ⭐️", callback_data="stars_50")],
        [InlineKeyboardButton("100 ⭐️", callback_data="stars_100")],
        [InlineKeyboardButton("500 ⭐️", callback_data="stars_500")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение с кнопками
    await context.bot.send_message(
        chat_id=chat_id,
        text=stars_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )




async def handle_stars_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора количества звезд.
    
    Создает инвойс для оплаты выбранного количества звезд.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Отвечаем на callback query
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
    
    # Получаем chat_id, user_id и user_name
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"
    
    # Извлекаем количество звезд из callback_data
    callback_data = update.callback_query.data
    stars_amount = int(callback_data.split('_')[1])  # "stars_50" -> 50
    
    # Создаем инвойс для оплаты звездами
    # Согласно документации, для цифровых товаров используем валюту "XTR" (Telegram Stars)
    try:
        invoice_keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"Внести ⭐️{stars_amount}", pay=True)]]
        )
        await context.bot.send_invoice(
            chat_id=chat_id,
            title="Поддержка YogaDailyBot",
            description=f"Спасибо за желание поддержать проект 🧡",
            payload=f"donation_{user_id}_{stars_amount}",  # Уникальный payload для отслеживания
            provider_token="",  # Для цифровых товаров оставляем пустым
            currency="XTR",  # Telegram Stars
            prices=[{"label": f"{stars_amount} ⭐️", "amount": stars_amount}],
            start_parameter=f"donation_{stars_amount}",  # Параметр для deep linking
            reply_markup=invoice_keyboard,
            is_flexible=False,  # Фиксированная цена
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            send_phone_number_to_provider=False,
            send_email_to_provider=False
        )
    except Exception as e:
        # Если произошла ошибка, отправляем сообщение об ошибке
        error_text = (
            "🚨 *Ошибка при создании инвойса*\n\n"
            "К сожалению, не удалось создать инвойс для оплаты. "
            "Попробуй еще раз или используй перевод по номеру карты."
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=error_text,
            parse_mode='Markdown'
        )


async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик pre-checkout query для подтверждения оплаты.
    
    Согласно документации, бот должен ответить на pre_checkout_query в течение 10 секунд.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    query = update.pre_checkout_query
    
    # Проверяем, что это донат (payload начинается с "donation_")
    if query.invoice_payload.startswith("donation_"):
        # Подтверждаем оплату
        await query.answer(ok=True)
    else:
        # Отклоняем оплату с объяснением
        await query.answer(
            ok=False, 
            error_message="Неизвестный тип платежа. Пожалуйста, попробуйте еще раз."
        )


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик успешной оплаты.
    
    Отправляет сообщение благодарности после успешной оплаты звездами.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    payment = update.message.successful_payment
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name or "друг"
    
    # Извлекаем информацию о платеже
    stars_amount = payment.total_amount
    payload = payment.invoice_payload
