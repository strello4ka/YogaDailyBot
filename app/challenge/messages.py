"""Формирование текста утренней сводки челленджа."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Literal, Optional

SummaryKind = Literal["daily", "intermediate", "final"]

SUMMARY_HOUR = 10
SUMMARY_MINUTE = 10
CHALLENGE_DURATION = 28
INTERMEDIATE_DAYS = frozenset({8, 15, 22})
FINAL_DAY = 28
WEEKLY_PROGRESS_DAYS = 7

SCHEDULE_HOUR = 20
SCHEDULE_MINUTE = 0
WEEKDAY_FULL_LABELS = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)

TELEGRAM_MESSAGE_LIMIT = 4096


@dataclass(frozen=True)
class ChallengeParticipant:
    user_id: int
    user_name: Optional[str]
    user_nickname: Optional[str]
    challenge_day: int


@dataclass(frozen=True)
class ProgressRow:
    participant: ChallengeParticipant
    completed: int
    total: int


@dataclass(frozen=True)
class FinalRankRow:
    participant: ChallengeParticipant
    completed: int
    total: int
    rank: int
    label: str


def display_name(user_nickname: Optional[str], user_name: Optional[str]) -> str:
    """@nickname или имя, если ника нет."""
    if user_nickname:
        nick = user_nickname.strip().lstrip("@")
        if nick:
            return f"@{nick}"
    if user_name and user_name.strip():
        return user_name.strip()
    return "Участник"


def detect_summary_kind(group_challenge_day: int, stopped: bool) -> Optional[SummaryKind]:
    """Определяет тип утреннего поста по challenge_day группы."""
    if stopped:
        return None
    if group_challenge_day == FINAL_DAY:
        return "final"
    if group_challenge_day in INTERMEDIATE_DAYS:
        return "intermediate"
    if group_challenge_day < FINAL_DAY:
        return "daily"
    return None


def get_upcoming_week_day_range(group_challenge_day: int) -> Optional[tuple[int, int]]:
    """Диапазон дней челленджа на ближайшую неделю (для воскресного расписания)."""
    if group_challenge_day >= CHALLENGE_DURATION:
        return None
    from_day = group_challenge_day + 1
    if from_day > CHALLENGE_DURATION:
        return None
    to_day = min(group_challenge_day + 7, CHALLENGE_DURATION)
    return from_day, to_day


def challenge_day_weekday_label(challenge_day: int) -> str:
    """Название дня недели: день 1 = Понедельник, день 2 = Вторник, …"""
    return WEEKDAY_FULL_LABELS[(challenge_day - 1) % 7]


def rank_final_results(progress_rows: list[ProgressRow]) -> list[FinalRankRow]:
    """Competition ranking: при равенстве — общее место; топ-2 с номером, остальные «молодец»."""
    sorted_rows = sorted(
        progress_rows,
        key=lambda r: (-r.completed, display_name(r.participant.user_nickname, r.participant.user_name)),
    )
    ranked: list[FinalRankRow] = []
    rank = 1
    i = 0
    while i < len(sorted_rows):
        j = i + 1
        while j < len(sorted_rows) and sorted_rows[j].completed == sorted_rows[i].completed:
            j += 1
        for k in range(i, j):
            row = sorted_rows[k]
            label = f"{rank} место" if rank <= 2 else "молодец"
            ranked.append(
                FinalRankRow(
                    participant=row.participant,
                    completed=row.completed,
                    total=row.total,
                    rank=rank,
                    label=label,
                )
            )
        rank = j + 1
        i = j
    return ranked


def _join_names_with_limit(names: list[str], max_names_length: int = 3500) -> str:
    if not names:
        return ""
    names_text = ", ".join(names)
    if len(names_text) <= max_names_length:
        return names_text
    truncated: list[str] = []
    current_len = 0
    for name in names:
        part = name if not truncated else f", {name}"
        if current_len + len(part) + 1 > max_names_length:
            break
        truncated.append(name)
        current_len += len(part)
    return ", ".join(truncated) + ", …"


def build_summary_message(
    kind: SummaryKind,
    participants: list[ChallengeParticipant],
    yesterday_done_ids: set[int],
    progress_rows: Optional[list[ProgressRow]] = None,
    final_rows: Optional[list[FinalRankRow]] = None,
    max_names_length: int = 3500,
) -> str:
    """Собирает текст утренней сводки по типу."""
    text = "Доброе утро, йоги ☀️\n\n"

    if kind == "daily":
        total = len(participants)
        done = [p for p in participants if p.user_id in yesterday_done_ids]
        not_done = [p for p in participants if p.user_id not in yesterday_done_ids]
        done_names = _join_names_with_limit(
            [display_name(p.user_nickname, p.user_name) for p in done],
            max_names_length,
        )
        not_done_names = _join_names_with_limit(
            [display_name(p.user_nickname, p.user_name) for p in not_done],
            max_names_length,
        )

        if done_names:
            text += (
                f"Итоги за вчера:\n"
                f"🔋 Выполнили практику {len(done)} из {total} участников: {done_names}"
            )
        else:
            text += (
                "Итоги за вчера:\n"
                f"🔋 Выполнили практику 0 из {total} участников"
            )

        if not_done_names:
            text += f"\n🪫 Не выполнили {len(not_done)} из {total}: {not_done_names}"

    if kind == "intermediate" and progress_rows is not None:
        progress_lines = "\n".join(
            f"• {display_name(row.participant.user_nickname, row.participant.user_name)}"
            f" — {row.completed}/{row.total} дней"
            for row in progress_rows
        )
        text += f"Промежуточные итоги челленджа:\n{progress_lines}\n\nВы прекрасны! Продолжайте!"

    if kind == "final" and final_rows is not None:
        final_lines = "\n".join(
            f"• {display_name(row.participant.user_nickname, row.participant.user_name)}"
            f" — {row.completed}/{row.total} дней — {row.label}"
            for row in final_rows
        )
        text += (
            f"Поздравляю всех с окончанием челленджа ✨\n"
            f"Итоги:\n"
            f"{final_lines}"
        )

    if len(text) > TELEGRAM_MESSAGE_LIMIT:
        text = text[: TELEGRAM_MESSAGE_LIMIT - 1] + "…"
    return text


def build_weekly_progress_rows(
    participants: list[ChallengeParticipant],
    completed_by_user_id: dict[int, int],
) -> list[ProgressRow]:
    """Прогресс за прошедшую неделю (7 дней) для еженедельной сводки."""
    rows = [
        ProgressRow(
            participant=p,
            completed=completed_by_user_id.get(p.user_id, 0),
            total=WEEKLY_PROGRESS_DAYS,
        )
        for p in participants
    ]
    rows.sort(
        key=lambda r: (-r.completed, display_name(r.participant.user_nickname, r.participant.user_name))
    )
    return rows


def build_progress_rows(
    participants: list[ChallengeParticipant],
    completed_by_user_id: dict[int, int],
) -> list[ProgressRow]:
    """Промежуточный прогресс N/M для каждого участника."""
    rows = [
        ProgressRow(
            participant=p,
            completed=completed_by_user_id.get(p.user_id, 0),
            total=p.challenge_day,
        )
        for p in participants
    ]
    rows.sort(
        key=lambda r: (-r.completed, display_name(r.participant.user_nickname, r.participant.user_name))
    )
    return rows


def build_final_rows(
    participants: list[ChallengeParticipant],
    completed_by_user_id: dict[int, int],
) -> list[FinalRankRow]:
    """Финальный рейтинг с competition ranking."""
    progress = [
        ProgressRow(
            participant=p,
            completed=completed_by_user_id.get(p.user_id, 0),
            total=CHALLENGE_DURATION,
        )
        for p in participants
    ]
    return rank_final_results(progress)


def build_weekly_schedule_message(
    from_day: int,
    to_day: int,
    practices: list[tuple[int, str, str, int]],
) -> str:
    """Расписание на неделю: день и длительность (жирным), заголовок, канал."""
    blocks = ["📅 Расписание на неделю:\n"]
    for day, title, channel_name, minutes in practices:
        weekday = challenge_day_weekday_label(day)
        title_text = html.escape((title or "Практика").strip())
        channel_text = html.escape((channel_name or "—").strip())
        blocks.append(
            f"<b>{html.escape(weekday)}: {minutes} мин</b>\n"
            f"{title_text}\n"
            f"{channel_text}"
        )
    return "\n\n".join(blocks)


def collect_summary_data(
    participants_raw: list[tuple],
    yesterday_done_ids: set[int],
    group_challenge_day: int,
    stopped: bool,
    completed_by_user_id: dict[int, int],
) -> tuple[Optional[SummaryKind], str]:
    """Определяет тип поста и возвращает текст сообщения."""
    participants = [
        ChallengeParticipant(
            user_id=row[0],
            user_name=row[1],
            user_nickname=row[2],
            challenge_day=int(row[3]),
        )
        for row in participants_raw
    ]
    if not participants:
        return None, ""

    kind = detect_summary_kind(group_challenge_day, stopped)
    if kind is None:
        return None, ""

    progress_rows = None
    final_rows = None
    if kind == "intermediate":
        progress_rows = build_weekly_progress_rows(participants, completed_by_user_id)
    elif kind == "final":
        final_rows = build_final_rows(participants, completed_by_user_id)

    text = build_summary_message(
        kind,
        participants,
        yesterday_done_ids,
        progress_rows=progress_rows,
        final_rows=final_rows,
    )
    return kind, text
