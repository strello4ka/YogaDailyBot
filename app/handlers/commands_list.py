"""Админ-команда /commands — памятка по всем командам бота."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.secret import ADMIN_USER_ID

logger = logging.getLogger(__name__)

COMMANDS_HELP_TEXT = (
    "*📋 Все команды бота*\n\n"
    "*Для пользователей*\n"
    "`/start` — онбординг или показ общей клавиатуры\n"
    "`/help` — помощь и советы\n"
    "`/progress` — прогресс практик (в челлендже ещё N/28)\n"
    "`/favorite` — избранные практики\n"
    "`/schedule` — управление расписанием\n"
    "`/practice` — как открыть кнопки выбора практики\n"
    "`/suggest` — предложить практику с YouTube (прямая команда)\n"
    "`/donate` — управление подпиской; пока донаты\n"
    "`/change_mode` — устаревшая команда, открывает новый интерфейс\n"
    "`/challenge` — запасной вход в текущий поток\n"
    "`/challenge_off` — досрочный выход из челленджа\n\n"
    "*Служебные*\n"
    "`/test` — сразу отправить тестовую практику\n"
    "`/myid` — показать user\\_id и chat\\_id\n\n"
    "*Админ*\n"
    "`/commands` — этот список\n"
    "`/secret` — массовая рассылка\n"
    "`/secret_delete` — удалить последнюю рассылку\n"
    "`/secret_edit` — изменить текст/подпись последней рассылки\n"
    "`/flow_add` — массовая запись в поток (далее список @ник / id)\n"
    "`/challenge_summary_preview` — сразу отправить сводку в группу\n"
    "`/challenge_final_resend` — повторно отправить исправленный финал 24.08.2026\n"
    "`/challenge_summary_reset` — сброс флагов сводок перед новым потоком\n"
    "`/challenge_schedule_preview` — превью воскресного расписания в группу"
)


async def commands_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает админу список всех команд бота."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        logger.warning(
            "Попытка использования /commands пользователем %s (не администратор)",
            user_id,
        )
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    await update.message.reply_text(COMMANDS_HELP_TEXT, parse_mode="Markdown")
