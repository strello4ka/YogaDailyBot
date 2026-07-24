"""Админ-команда массовой записи в поток: /flow_add."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.secret import ADMIN_USER_ID
from app.challenge.cohort import (
    cohort_not_configured_message,
    get_challenge_start_practice_id,
    is_cohort_configured,
)
from app.challenge.flow.start_flow import send_challenge_welcome_dm
from data.db import find_user_for_challenge_enroll, get_yoga_practice_by_id

logger = logging.getLogger(__name__)

WAITING_FOR_FLOW_ADD_KEY = "waiting_for_flow_add"


async def flow_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Массовая запись в поток: следующим сообщением список @ник / user_id по строке."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    if not is_cohort_configured():
        await update.message.reply_text(cohort_not_configured_message())
        return

    practice_id = get_challenge_start_practice_id()
    if not get_yoga_practice_by_id(practice_id):
        await update.message.reply_text(
            f"❌ Практика CHALLENGE_START_PRACTICE_ID={practice_id} не найдена в базе."
        )
        return

    context.user_data[WAITING_FOR_FLOW_ADD_KEY] = True
    await update.message.reply_text(
        "📋 *Массовая запись в челлендж*\n\n"
        f"Стартовая практика потока: *{practice_id}*\n\n"
        "Пришли следующим сообщением список участников — *по одному на строку*:\n"
        "• `@nickname` или `nickname`\n"
        "• или числовой `user_id`\n\n"
        "Каждому найденному уйдёт приветствие и выбор времени.",
        parse_mode="Markdown",
    )
    logger.info("Админ %s начал массовую запись в челлендж (/flow_add)", user_id)


def _parse_enroll_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for line in (text or "").splitlines():
        part = line.strip()
        if not part or part.startswith("#"):
            continue
        tokens.append(part)
    return tokens


async def handle_flow_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает список участников после /flow_add."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        return
    if not context.user_data.get(WAITING_FOR_FLOW_ADD_KEY):
        return

    context.user_data.pop(WAITING_FOR_FLOW_ADD_KEY, None)

    if not is_cohort_configured():
        await update.message.reply_text(cohort_not_configured_message())
        return

    practice_id = get_challenge_start_practice_id()
    tokens = _parse_enroll_tokens(update.message.text or "")
    if not tokens:
        await update.message.reply_text("Список пуст. Отправь /flow_add ещё раз.")
        return

    ok_lines: list[str] = []
    fail_lines: list[str] = []

    for token in tokens:
        row = find_user_for_challenge_enroll(token)
        if not row:
            fail_lines.append(f"• {token} — не найден в базе")
            continue
        target_user_id, chat_id, user_name, user_nickname = row
        if not chat_id:
            fail_lines.append(f"• {token} — нет chat_id")
            continue
        ok, err = await send_challenge_welcome_dm(
            context,
            user_id=int(target_user_id),
            chat_id=int(chat_id),
            practice_id=practice_id,
            user_name=user_name,
            user_nickname=user_nickname,
        )
        label = f"@{user_nickname}" if user_nickname else str(target_user_id)
        if ok:
            ok_lines.append(f"• {label}")
        else:
            fail_lines.append(f"• {token} ({label}) — {err}")

    report = (
        f"✅ Записаны и получили сообщение ({len(ok_lines)}):\n"
        + ("\n".join(ok_lines) if ok_lines else "—")
        + f"\n\n❌ Не удалось ({len(fail_lines)}):\n"
        + ("\n".join(fail_lines) if fail_lines else "—")
    )
    if len(report) > 4000:
        report = report[:3990] + "\n…"
    await update.message.reply_text(report)
    logger.info(
        "Массовая запись челленджа (/flow_add): ok=%s fail=%s",
        len(ok_lines),
        len(fail_lines),
    )
