"""Команда /change_mode — снова выбрать Daily или By mood (без сброса прогресса)."""

from telegram import Update
from telegram.ext import ContextTypes

from app.keyboards import get_mode_choice_keyboard


async def change_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает выбор режима. Прогресс не трогаем — полный сброс только по /start."""
    user_id = update.effective_user.id if update.effective_user else None
    time_choice_chat_id = context.user_data.pop("daily_time_choice_chat_id", None)
    time_choice_message_id = context.user_data.pop("daily_time_choice_message_id", None)
    if time_choice_chat_id and time_choice_message_id:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=time_choice_chat_id,
                message_id=time_choice_message_id,
                reply_markup=None,
            )
        except Exception as e:
            print(f"Не удалось убрать кнопку выбора времени после /change_mode: {e}")

    if user_id and context.user_data.get("waiting_for_time"):
        from app.onboarding import cancel_reminders

        await cancel_reminders(context, user_id)

    context.user_data.pop("waiting_for_practice_suggestion", None)
    context.user_data.pop("waiting_for_time", None)
    context.user_data.pop("is_time_change", None)

    await update.message.reply_text(
        "*Выбери режим работы бота:*\n\n"
        "🌀 Режим *Daily* — для тех, кто хочет мягко внедрить привычку заниматься ежедневно и не перегорать.\n"
        "*Выбираешь удобное время, и бот присылает практику в это время каждый день.*\n"
        "Неделя содержит сбалансированный набор практик:\n"
        "• 2-3 бодрые, 5-15 минут\n"
        "• по вторникам - всегда работа с осанкой, спиной и шеей\n"
        "• по пятницам - что-то необычное для развития кругозора и получения нового опыта\n"
        "• по субботам - горячая активная, 20-25 минут\n"
        "• по воскресеньям - релакс, 20-25 минут\n"
        "• плюс бонус - приходит один раз в неделю в дополнение к основной практике: дыхательная техника, медитация, отстройка асан, изучение балансов на руках.\n"
        "*Ты не заметишь напряга, но тело скажет \"спасибо\" и отблагодарит отражением в зеркале!*\n\n"
        "🌀 Режим *By mood* — для тех, кто хочет делать зарядки и разминки по состоянию \"здесь и сейчас\", но без траты времени на поиск качественного контента.\n"
        "*Нажимаешь кнопку по настроению, и бот сразу подбирает подходящую практику под твой запрос*: \"Ленивые дни\", \"Пятиминутка\", \"Практика дня\" и т.д. Также можно самому настроить время и интенсивность.\n\n"
        "Оба режима помогают практиковать регулярно, просто разным способом:\n"
        "*Daily* — через привычку и стабильность\n"
        "*By mood* — через гибкость и свободу выбора.\n\n"
        "Выбирай то, что ближе тебе сейчас, и *жми кнопку* 👇 \n"
        "(изменить режим можно в любой момент в меню)",
        reply_markup=get_mode_choice_keyboard(),
        parse_mode="Markdown",
    )
