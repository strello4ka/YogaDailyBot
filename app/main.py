"""Entrypoint for YogaDailyBot.
Main application file that initializes the bot and registers all handlers.
"""

import asyncio
import logging
import re
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, PreCheckoutQueryHandler, ChatMemberHandler, filters, ContextTypes
from telegram import Update

from .config import BOT_TOKEN
from .onboarding import (
    start_command,
    start_restart_yes_callback,
    start_restart_no_callback,
    want_start_callback,
    handle_time_input,
    onboarding_open_mode_choice_callback,
    onboarding_show_example_callback,
    mode_pick_daily_callback,
    mode_pick_by_mood_callback,
)
from .daily.set_time import handle_time_change_input
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
from .handlers.done import (
    handle_practice_done_callback,
    schedule_done_evening_reminders,
    schedule_strip_done_buttons_midnight,
)
from .daily.pause import schedule_pause_reminders
from .by_mood.reminders import schedule_by_mood_reminders
from .handlers.change_mode import change_mode_command
from .handlers.progress import (
    handle_progress_reset_callback,
    handle_progress_reset_yes_callback,
    handle_progress_reset_no_callback,
)
from .handlers.secret import (
    secret_command,
    handle_secret_input,
    secret_delete_command,
    secret_edit_command,
    handle_secret_edit_input,
)
from .block import handle_user_block_event
from .schedule.scheduler import schedule_daily_practices, send_test_practice
from .challenge.jobs import schedule_challenge_jobs
from .challenge.summary.commands import (
    challenge_summary_preview_command,
    challenge_summary_reset_command,
)
from .challenge.week_schedule.commands import challenge_schedule_preview_command
from .challenge.flow.flow_add_command import (
    flow_add_command,
    handle_flow_add_input,
    WAITING_FOR_FLOW_ADD_KEY,
)
from .challenge.flow.hand_commands import (
    challenge_command,
    challenge_off_command,
)
from .challenge.flow.start_flow import (
    CHALLENGE_TIME_FLOW_KEY,
    handle_challenge_time_input,
)
from .handlers.suggest_practice import handle_suggest_practice_callback
from .handlers.donations import handle_donations_callback
from .handlers.progress import handle_progress_callback
from .handlers.help import help_command
from .handlers.commands_list import commands_list_command
from .handlers.favorites import (
    favorite_command,
    handle_fav_toggle_callback,
    handle_fav_nav_callback,
    handle_fav_noop_callback,
)
from .handlers.reactions import handle_practice_reaction_callback, reaction_stats_command
from .bot_commands import setup_bot_commands
from app.by_mood.self_decide import handle_difficulty_callback as by_mood_self_difficulty_callback
from app.by_mood.self_decide import handle_time_callback as by_mood_self_time_callback
from app.daily.extra_practices import (
    handle_extra_mood_callback,
    handle_extra_self_difficulty_callback,
    handle_extra_self_time_callback,
)


async def suggest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_suggest_practice_callback(update, context)


async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_donations_callback(update, context)


async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_progress_callback(update, context)


async def favorite_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await favorite_command(update, context)


async def handle_text_input(update: Update, context):
    """Универсальный обработчик текстовых сообщений.
    
    Определяет, какой обработчик вызвать на основе состояния пользователя.
    """
    print(f"=== DEBUG: handle_text_input вызвана ===")
    print(f"Message text: '{update.message.text}'")
    print(f"User data: {context.user_data}")

    # Проверяем состояние ожидания редактирования рассылки
    if context.user_data.get('waiting_for_secret_edit'):
        await handle_secret_edit_input(update, context)
        return
    # Проверяем состояние ожидания рассылки
    if context.user_data.get('waiting_for_secret'):
        print("=== DEBUG: Переадресация на handle_secret_input ===")
        await handle_secret_input(update, context)
        return

    if context.user_data.get(WAITING_FOR_FLOW_ADD_KEY):
        await handle_flow_add_input(update, context)
        return
    
    # Проверяем состояние ожидания предложения практики
    if context.user_data.get('waiting_for_practice_suggestion'):
        print("=== DEBUG: Переадресация на handle_practice_suggestion_input ===")
        await handle_practice_suggestion_input(update, context)
        return
    
    # Проверяем состояние ожидания ввода времени
    if context.user_data.get('waiting_for_time'):
        if context.user_data.get(CHALLENGE_TIME_FLOW_KEY):
            print("=== DEBUG: Переадресация на handle_challenge_time_input ===")
            await handle_challenge_time_input(update, context)
            return
        # Проверяем, это изменение времени или онбординг
        if context.user_data.get('is_time_change'):
            print("=== DEBUG: Переадресация на handle_time_change_input (изменение времени) ===")
            await handle_time_change_input(update, context)
        else:
            print("=== DEBUG: Переадресация на handle_time_input (онбординг) ===")
            await handle_time_input(update, context)
        return

    from data.db import get_user_bot_mode, is_user_onboarding_required

    if (
        update.effective_user
        and get_user_bot_mode(update.effective_user.id) == "challenge"
        and is_user_onboarding_required(update.effective_user.id)
    ):
        print("=== DEBUG: Переадресация на handle_challenge_time_input (challenge из БД) ===")
        await handle_challenge_time_input(update, context)
        return

    if (
        update.effective_user
        and is_user_onboarding_required(update.effective_user.id)
        and get_user_bot_mode(update.effective_user.id) in ("pending", "daily")
    ):
        from app.onboarding import validate_time_format

        is_valid, _ = validate_time_format(update.message.text or "")
        if is_valid:
            print("=== DEBUG: Переадресация на handle_time_input (время без кнопки) ===")
            await handle_time_input(update, context)
            return

    print("=== DEBUG: Никакое состояние не установлено, сообщение игнорируется ===")
    # Если никакое состояние не установлено, сбрасываем возможные "зависшие" состояния
    # и игнорируем сообщение (это может быть обычное сообщение пользователя)
    context.user_data.pop('waiting_for_practice_suggestion', None)
    context.user_data.pop('waiting_for_time', None)
    context.user_data.pop('waiting_for_secret', None)
    context.user_data.pop('waiting_for_secret_edit', None)
    context.user_data.pop(WAITING_FOR_FLOW_ADD_KEY, None)

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


def main():
    """Основная функция запуска бота."""
    # Создаем приложение с JobQueue
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(setup_bot_commands)
        .build()
    )

    # Блокировка / разблокировка бота пользователем
    application.add_handler(
        ChatMemberHandler(handle_user_block_event, ChatMemberHandler.MY_CHAT_MEMBER),
        group=-1,
    )

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("change_mode", change_mode_command))
    application.add_handler(CommandHandler("suggest", suggest_command))
    application.add_handler(CommandHandler("donate", donate_command))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("favorite", favorite_command_handler))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("test", test_practice_command))
    application.add_handler(CommandHandler("myid", myid_command))
    application.add_handler(CommandHandler("secret", secret_command))
    application.add_handler(CommandHandler("secret_delete", secret_delete_command))
    application.add_handler(CommandHandler("secret_edit", secret_edit_command))
    application.add_handler(CommandHandler("reaction_stats", reaction_stats_command))
    application.add_handler(CommandHandler("challenge", challenge_command))
    application.add_handler(CommandHandler("challenge_off", challenge_off_command))
    application.add_handler(CommandHandler("flow_add", flow_add_command))
    application.add_handler(CommandHandler("challenge_summary_preview", challenge_summary_preview_command))
    application.add_handler(CommandHandler("challenge_summary_reset", challenge_summary_reset_command))
    application.add_handler(CommandHandler("challenge_schedule_preview", challenge_schedule_preview_command))
    application.add_handler(CommandHandler("commands", commands_list_command))
    
    # Регистрируем обработчики callback-запросов (онбординг и выбор режима)
    application.add_handler(CallbackQueryHandler(start_restart_yes_callback, pattern="^start_restart_yes$"))
    application.add_handler(CallbackQueryHandler(start_restart_no_callback, pattern="^start_restart_no$"))
    application.add_handler(CallbackQueryHandler(onboarding_show_example_callback, pattern="^onboarding_show_example$"))
    application.add_handler(CallbackQueryHandler(onboarding_open_mode_choice_callback, pattern="^onboarding_open_mode_choice$"))
    application.add_handler(CallbackQueryHandler(mode_pick_daily_callback, pattern="^mode_pick_daily$"))
    application.add_handler(CallbackQueryHandler(mode_pick_by_mood_callback, pattern="^mode_pick_by_mood$"))
    application.add_handler(CallbackQueryHandler(want_start_callback, pattern="^want_start$"))
    application.add_handler(CallbackQueryHandler(by_mood_self_time_callback, pattern="^self_time:"))
    application.add_handler(CallbackQueryHandler(by_mood_self_difficulty_callback, pattern="^self_difficulty:"))
    application.add_handler(CallbackQueryHandler(handle_extra_mood_callback, pattern="^extra_mood:"))
    application.add_handler(CallbackQueryHandler(handle_extra_self_time_callback, pattern="^extra_self_time:"))
    application.add_handler(
        CallbackQueryHandler(handle_extra_self_difficulty_callback, pattern="^extra_self_difficulty:")
    )

    # Регистрируем обработчики для донатов
    application.add_handler(CallbackQueryHandler(handle_donate_card_callback, pattern="^donate_card$"))
    application.add_handler(CallbackQueryHandler(handle_donate_stars_callback, pattern="^donate_stars$"))
    
    # Регистрируем обработчики для выбора количества звезд
    application.add_handler(CallbackQueryHandler(handle_stars_amount_callback, pattern="^stars_"))

    # Трекер прогресса: кнопка «✅ Я сделал!» и «Мой прогресс» / сброс
    application.add_handler(CallbackQueryHandler(handle_practice_done_callback, pattern="^practice_done"))
    application.add_handler(CallbackQueryHandler(handle_fav_toggle_callback, pattern="^fav_toggle:"))
    application.add_handler(CallbackQueryHandler(handle_practice_reaction_callback, pattern="^practice_(like|dislike):"))
    application.add_handler(CallbackQueryHandler(handle_fav_nav_callback, pattern="^fav_nav:"))
    application.add_handler(CallbackQueryHandler(handle_fav_noop_callback, pattern="^fav_noop$"))
    application.add_handler(CallbackQueryHandler(handle_progress_reset_callback, pattern="^progress_reset$"))
    application.add_handler(CallbackQueryHandler(handle_progress_reset_yes_callback, pattern="^progress_reset_yes$"))
    application.add_handler(CallbackQueryHandler(handle_progress_reset_no_callback, pattern="^progress_reset_no$"))
    
    # Регистрируем обработчики для платежей
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    
    # Reply-кнопки Daily и By mood (один обработчик — внутри проверяется режим)
    reply_buttons = [
        "Изменить время",
        "Советы",
        "Пауза",
        "Еще практики",
        "Практика дня",
        "Без коврика",
        "Ленивые дни",
        "Мини",
        "Хард",
        "САМ решу",
        "strello4ka",
        "Длинные",
    ]
    escaped = [re.escape(b) for b in reply_buttons]
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(f"^({'|'.join(escaped)})$") & filters.ChatType.PRIVATE,
            handle_reply_button,
        )
    )
    
    # Регистрируем обработчик фото для массовой рассылки (с высоким приоритетом)
    # Этот обработчик проверяет состояние waiting_for_secret и обрабатывает фото с подписью
    async def handle_photo_or_text_for_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик фото и текста для массовой рассылки."""
        if context.user_data.get('waiting_for_secret_edit'):
            await handle_secret_edit_input(update, context)
            return
        if context.user_data.get('waiting_for_secret'):
            await handle_secret_input(update, context)
            return
        if context.user_data.get('waiting_for_practice_suggestion'):
            await update.message.reply_text(
                "🚨 Пока могу принять только текст в формате:\n"
                "\\*ссылка на видео\\*\n"
                "\\*комментарий (не обязательно)\\*",
                parse_mode='Markdown',
            )
            return
    
    # Регистрируем обработчик фото (для рассылки) с высоким приоритетом
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo_or_text_for_secret), group=1)
    
    # Текстовый ввод (время, suggest и т.д.) — только в личке, не в группах
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text_input)
    )
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Планируем ежедневную отправку практик
    schedule_daily_practices(application)
    # Планируем напоминания пользователям в режиме паузы (логика паузы живет в handlers/pause.py)
    schedule_pause_reminders(application)
    # Планируем напоминания неактивным пользователям в режиме By mood
    schedule_by_mood_reminders(application)
    schedule_challenge_jobs(application)
    # В 00:00 МСК снимаем «Я сделал!» со вчерашних (и более старых) неотмеченных практик
    schedule_strip_done_buttons_midnight(application)
    # Резервный раннер 19:30-напоминаний: восстанавливает отправку после перезапусков
    schedule_done_evening_reminders(application)
    
    # Запускаем бота
    logger.info("Запускаем YogaDailyBot с JobQueue...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
