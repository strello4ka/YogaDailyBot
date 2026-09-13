"""One-time delivery of the current reply keyboard to existing users."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.keyboards import COMMON_REPLY_KEYBOARD_VERSION, get_common_reply_keyboard
from data.db import mark_reply_keyboard_version, needs_reply_keyboard_refresh

logger = logging.getLogger(__name__)


async def refresh_old_user_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh an old completed user's keyboard, then let the original action continue."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    # /start сам запускает актуальный сценарий и в итоге устанавливает новую
    # клавиатуру. Не дублируем уведомление перед вопросом о перезапуске и при
    # нажатии его кнопок подтверждения.
    message_text = (update.effective_message.text or "") if update.effective_message else ""
    command = message_text.split(maxsplit=1)[0].split("@", 1)[0].lower() if message_text.strip() else ""
    if command == "/start":
        return
    callback_data = (update.callback_query.data or "") if update.callback_query else ""
    if callback_data.startswith("start_restart_"):
        return

    if not needs_reply_keyboard_refresh(user.id, COMMON_REPLY_KEYBOARD_VERSION):
        return

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text="Я обновился — теперь все практики и расписание всегда под рукой 🧡",
            reply_markup=get_common_reply_keyboard(),
        )
    except Exception:
        logger.exception("Не удалось обновить reply-клавиатуру user=%s", user.id)
        return
    mark_reply_keyboard_version(user.id, COMMON_REPLY_KEYBOARD_VERSION)
