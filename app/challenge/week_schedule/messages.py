"""Текст воскресного расписания челленджа на неделю."""

from __future__ import annotations

from telegram.helpers import escape_markdown

from app.challenge.cohort import challenge_day_weekday_label


def build_weekly_schedule_message(
    from_day: int,
    to_day: int,
    practices: list[tuple[int, str, str, int]],
) -> str:
    """Расписание на неделю: день и длительность (жирным), заголовок, канал."""
    day_blocks: list[str] = []
    for day, title, channel_name, minutes in practices:
        weekday = challenge_day_weekday_label(day)
        title_text = escape_markdown((title or "Практика").strip(), version=1)
        channel_text = escape_markdown((channel_name or "—").strip(), version=1)
        day_blocks.append(
            f"*🌀{weekday}: {minutes} мин*\n"
            f"{title_text}\n"
            f"{channel_text}"
        )
    body = "\n\n".join(day_blocks)
    if not body:
        return "📅 Расписание на неделю:"
    return f"📅 Расписание на неделю:\n\n{body}"
