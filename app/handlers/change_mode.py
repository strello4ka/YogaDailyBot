"""Команда /change_mode — снова выбрать Daily или By mood (без сброса прогресса)."""

from telegram import Update
from telegram.ext import ContextTypes

from app.challenge.challenge_commands import CHALLENGE_TIME_FLOW_KEY, PENDING_CHALLENGE_PRACTICE_KEY
from app.handlers.done import cancel_done_reminders, dismiss_done_reminders
from app.keyboards import get_mode_choice_keyboard
from app.onboarding import MODE_CHOICE_INTRO_MARKDOWN, schedule_mode_pick_reminders


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
    context.user_data.pop(CHALLENGE_TIME_FLOW_KEY, None)
    context.user_data.pop(PENDING_CHALLENGE_PRACTICE_KEY, None)

    chat_id = update.effective_chat.id
    if user_id:
        await cancel_done_reminders(context, user_id)
        dismiss_done_reminders(user_id)

    await update.message.reply_text(
        MODE_CHOICE_INTRO_MARKDOWN,
        reply_markup=get_mode_choice_keyboard(),
        parse_mode="Markdown",
    )

    if user_id:
        await schedule_mode_pick_reminders(
            context, chat_id, user_id, from_change_mode=True
        )
