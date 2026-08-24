"""Админ-команды утренней сводки: preview и reset."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.config import CHALLENGE_GROUP_CHAT_ID
from app.handlers.secret import ADMIN_USER_ID
from app.challenge.cohort import CHALLENGE_DURATION, FINAL_SUMMARY_DAY
from app.challenge.summary.job import send_challenge_group_summary
from app.challenge.summary.messages import collect_summary_data
from data.db import (
    find_user_for_challenge_enroll,
    get_challenge_completed_in_last_n_days,
    reset_challenge_summary_state,
)

logger = logging.getLogger(__name__)


# Разовая безопасная повторная отправка финала потока, завершившегося 24.08.2026.
# После автозавершения challenge_start_id очищен, поэтому обычный preview уже не
# может восстановить состав участников.
FINAL_RESEND_NICKNAMES_2026_08_24 = (
    "marimortis",
    "anya_sarachai",
    "ilmiraz",
    "Steelijah",
    "akimova_kseniya",
    "olya_vinnikova",
    "Kisshmissh",
    "prikashchenkova",
    "alinavarich",
    "artemburda",
    "dariyasmirnovaa",
    "liyoook",
    "k_turchinskaya",
    "victoriazolotareva",
    "sunrisie",
    "zaytseva_polina",
    "fedotovasia",
    "didipiepink",
    "yanayashinaaa",
    "zmn_chris",
    "strello4ka",
    "helentajj",
)


async def challenge_summary_preview_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сводку сразу (без ожидания 10:10), не меняя флаги отправки."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    ok = await send_challenge_group_summary(context, force=True)
    if ok:
        await update.message.reply_text("✅ Превью сводки отправлено в групповой чат.")
    else:
        await update.message.reply_text(
            "❌ Не удалось отправить сводку. Проверь CHALLENGE_GROUP_CHAT_ID, участников челленджа и логи."
        )


async def challenge_summary_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбрасывает флаги остановки и последней отправки для нового потока челленджа."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    if reset_challenge_summary_state():
        await update.message.reply_text("✅ Флаги сводок и расписания сброшены.")
        logger.info("Админ %s сбросил состояние сводки челленджа", user_id)
    else:
        await update.message.reply_text("❌ Не удалось сбросить состояние сводки.")


async def challenge_final_resend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повторно отправляет исправленный финал, не меняя пользователей и флаги."""
    user_id = update.effective_user.id if update.effective_user else None
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    if not CHALLENGE_GROUP_CHAT_ID:
        await update.message.reply_text("❌ CHALLENGE_GROUP_CHAT_ID не задан.")
        return

    try:
        group_chat_id = int(CHALLENGE_GROUP_CHAT_ID)
    except ValueError:
        await update.message.reply_text("❌ CHALLENGE_GROUP_CHAT_ID должен быть числом.")
        return

    participants_raw = []
    missing = []
    seen_user_ids = set()
    for nickname in FINAL_RESEND_NICKNAMES_2026_08_24:
        user = find_user_for_challenge_enroll(nickname)
        if not user:
            missing.append(f"@{nickname}")
            continue

        participant_id, _chat_id, user_name, stored_nickname = user
        if participant_id in seen_user_ids:
            continue
        seen_user_ids.add(participant_id)
        participants_raw.append((participant_id, user_name, stored_nickname, 0))

    if missing:
        await update.message.reply_text(
            "❌ Сводка не отправлена: не найдены участники:\n" + ", ".join(missing)
        )
        return

    completed_by_user_id = {
        participant[0]: get_challenge_completed_in_last_n_days(
            participant[0], CHALLENGE_DURATION
        )
        for participant in participants_raw
    }
    kind, text = collect_summary_data(
        participants_raw,
        yesterday_done_ids=set(),
        group_challenge_day=FINAL_SUMMARY_DAY,
        stopped=False,
        completed_by_user_id=completed_by_user_id,
    )
    if kind != "final" or not text:
        await update.message.reply_text("❌ Не удалось сформировать финальную сводку.")
        return

    try:
        await context.bot.send_message(chat_id=group_chat_id, text=text)
    except Exception as exc:
        logger.error(
            "Ошибка повторной отправки финала челленджа в чат %s: %s",
            group_chat_id,
            exc,
        )
        await update.message.reply_text("❌ Не удалось отправить сводку в групповой чат.")
        return

    logger.info(
        "Админ %s повторно отправил финал челленджа для %s участников",
        user_id,
        len(participants_raw),
    )
    await update.message.reply_text("✅ Исправленная финальная сводка отправлена в групповой чат.")
