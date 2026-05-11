"""Команда /change_mode — снова выбрать Daily или By mood (без сброса прогресса)."""

from telegram import Update
from telegram.ext import ContextTypes

from app.keyboards import MODE_CHOICE_INTRO_MARKDOWN, get_mode_choice_keyboard
from app.mode.challenge import PENDING_CHALLENGE_PRACTICE_KEY


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
    context.user_data.pop(PENDING_CHALLENGE_PRACTICE_KEY, None)

    await update.message.reply_text(
        MODE_CHOICE_INTRO_MARKDOWN,
        reply_markup=get_mode_choice_keyboard(),
        parse_mode="Markdown",
    )
