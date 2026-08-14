"""Лайк и дизлайк практики."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.practice_ref import parse_practice_callback
from data.db import (
    get_practice_by_catalog,
    get_practice_reaction_stats,
    set_user_practice_reaction,
)

logger = logging.getLogger(__name__)

REACTION_TOASTS = {
    "like": "👍 Запомнил, тебе понравилось",
    "dislike": "👎 Понял, не зашло",
}


async def reaction_stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Показывает администратору сводку уникальных реакций по практикам."""
    from app.handlers.secret import ADMIN_USER_ID

    user = update.effective_user
    message = update.effective_message
    if not user or not message:
        return
    if user.id != ADMIN_USER_ID:
        await message.reply_text("❌ У тебя нет доступа к этой команде.")
        return

    rows = get_practice_reaction_stats()
    if not rows:
        await message.reply_text("Реакций на практики пока нет.")
        return

    lines = ["Реакции на практики:", ""]
    for practice_id, catalog, title, channel, likes, dislikes, total in rows:
        label = title or "Практика"
        channel_suffix = f" · {channel}" if channel else ""
        lines.append(
            f"{label}{channel_suffix} [{catalog}:{practice_id}] — "
            f"👍 {likes} · 👎 {dislikes} · всего {total}"
        )

    chunks = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > 3900:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    for chunk in chunks:
        await message.reply_text(chunk)


async def handle_practice_reaction_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Сохраняет одну уникальную текущую реакцию на практику."""
    query = update.callback_query
    user = update.effective_user
    if not query or not query.data or not user:
        return

    if query.data.startswith("practice_like:"):
        prefix = "practice_like"
        reaction = "like"
    elif query.data.startswith("practice_dislike:"):
        prefix = "practice_dislike"
        reaction = "dislike"
    else:
        await query.answer("Ошибка.")
        return

    practice_id, practice_catalog = parse_practice_callback(query.data, prefix)
    if practice_id is None:
        await query.answer("Ошибка.")
        return
    if not get_practice_by_catalog(practice_id, practice_catalog):
        await query.answer("Практика больше не доступна.")
        return

    if set_user_practice_reaction(
        user.id,
        practice_id,
        reaction,
        practice_catalog,
    ):
        await query.answer(REACTION_TOASTS[reaction])
    else:
        logger.error(
            "Не удалось сохранить реакцию user=%s practice=%s catalog=%s reaction=%s",
            user.id,
            practice_id,
            practice_catalog,
            reaction,
        )
        await query.answer("Не удалось сохранить реакцию. Попробуй ещё раз.")
