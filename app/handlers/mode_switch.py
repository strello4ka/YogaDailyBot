"""Команда /change_mode — снова выбрать Daily или By mood (без сброса прогресса)."""

from telegram import Update
from telegram.ext import ContextTypes

from app.keyboards import get_mode_choice_keyboard


async def change_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает выбор режима. Прогресс не трогаем — полный сброс только по /start."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id and context.user_data.get("waiting_for_time"):
        from app.onboarding import cancel_reminders

        await cancel_reminders(context, user_id)

    context.user_data.pop("waiting_for_practice_suggestion", None)
    context.user_data.pop("waiting_for_time", None)
    context.user_data.pop("is_time_change", None)
    context.user_data.pop("by_mood_self_step", None)
    context.user_data.pop("by_mood_self_time", None)

    await update.message.reply_text(
        "Выбери режим работы бота:\n"
        "*Daily* — по расписанию.\n"
        "*By mood* — практики по кнопкам, без рассылки по времени.\n\n",
        reply_markup=get_mode_choice_keyboard(),
        parse_mode="Markdown",
    )
