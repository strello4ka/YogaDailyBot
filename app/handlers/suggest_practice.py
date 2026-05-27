"""Handler for accepting user-suggested practice links."""

import re
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
        "*Хочешь, чтобы твоя любимая практика появилась в YogaDailyBot?*\n"
        "🔗 Поделись ссылкой, и я с радостью добавлю её!\n\n"
        "*Как предложить?*\n"
        "отправь сообщение в таком формате:\n"
        "\\*одна ссылка на видео\\*\n"
        "\\*любой комментарий (не обязательно)\\*\n\n"
        "*Пример:*\n"
        "https://youtu.be/oTzetTgYpSU?si=ewHrtkwVb4hFO1NG\n"
        "моя любимая-любимая практика, бодрит и поднимает настроение 🤤"
    )
    
    # Отправляем сообщение
    await context.bot.send_message(
        chat_id=chat_id,
        text=suggest_text,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    
    # Очищаем другие состояния перед установкой нового
    context.user_data.pop('waiting_for_time', None)
    
    # Устанавливаем состояние ожидания предложения практики
    context.user_data['waiting_for_practice_suggestion'] = True


def validate_video_url(url: str) -> tuple[bool, str]:
    """Проверяет формат ссылки на видео и возвращает результат валидации.
    
    Args:
        url: Строка с ссылкой на видео
        
    Returns:
        tuple: (is_valid, error_message или cleaned_url)
    """
    # Убираем пробелы
    url = url.strip()
    
    # Проверяем, что это ссылка на YouTube
    youtube_patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?youtube\.com/v/([a-zA-Z0-9_-]+)'
    ]
    
    for pattern in youtube_patterns:
        match = re.match(pattern, url)
        if match:
            # Возвращаем стандартизированную ссылку
            video_id = match.group(1)
            return True, f"https://youtu.be/{video_id}"
    
    return False, "Хм, это не похоже на ссылку на YouTube видео."


async def handle_practice_suggestion_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода предложения практики пользователем.
    
    Валидирует введенную ссылку и сохраняет предложение.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    # Проверяем, что пользователь в состоянии ожидания предложения практики
    if not context.user_data.get('waiting_for_practice_suggestion'):
        return
    
    # Получаем введенный текст
    message_text = update.message.text
    
    # Разделяем сообщение на строки
    lines = [line.strip() for line in message_text.split('\n') if line.strip()]
    
    if not lines:
        await update.message.reply_text(
            "🚨 Сообщение пустое.\n\n"
            "Попробуй еще раз в формате:\n"
            "\\*ссылка на видео\\*\n"
            "\\*комментарий (не обязательно)\\*"
        )
        return
    
    # Первая строка должна быть ссылкой
    video_url = lines[0]
    
    # Валидируем ссылку
    is_valid, result = validate_video_url(video_url)
    
    if not is_valid:
        await update.message.reply_text(
            f"🚨 {result}\n\n"
            "Попробуй еще раз в формате:\n"
            "\\*ссылка на видео\\*\n"
            "\\*комментарий (не обязательно)\\*",
            parse_mode='Markdown',
        )
        return
    
    # Получаем комментарий (если есть)
    comment = '\n'.join(lines[1:]) if len(lines) > 1 else None
    
    # Сохраняем предложение в базу данных
    user_id = update.effective_user.id
    # Получаем никнейм пользователя из Telegram (может быть None, если пользователь не установил username)
    user_nickname = update.effective_user.username
    
    from data.db import save_user_practice_suggestion
    save_success = save_user_practice_suggestion(user_id, result, comment, user_nickname)
    
    if not save_success:
        await update.message.reply_text(
            "🚨 Произошла ошибка при сохранении твоего предложения.\n"
            "Попробуй еще раз."
        )
        return
    
    # Убираем состояние ожидания
    context.user_data.pop('waiting_for_practice_suggestion', None)
    
    # Сообщение об успешном сохранении
    success_text = (
        "Есс, практика успешно добавлена и скоро появится в коллекции!\n"
        "Благодаря тебе я становлюсь ещё круче 🧡"
    )
    
    await update.message.reply_text(success_text)
