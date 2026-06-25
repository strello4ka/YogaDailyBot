"""Формирование текста утренней сводки челленджа."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

SummaryKind = Literal["daily", "intermediate", "final"]

SUMMARY_HOUR = 10
SUMMARY_MINUTE = 10
CHALLENGE_DURATION = 28
INTERMEDIATE_DAYS = frozenset({7, 14, 21})
FINAL_DAY = 28

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


def _format_yesterday_section(
    participants: list[ChallengeParticipant],
    yesterday_done_ids: set[int],
    max_names_length: int = 3500,
) -> str:
    total = len(participants)
    done = [p for p in participants if p.user_id in yesterday_done_ids]
    names = [display_name(p.user_nickname, p.user_name) for p in done]

    names_text = ", ".join(names)
    if len(names_text) > max_names_length:
        truncated: list[str] = []
        current_len = 0
        for name in names:
            part = name if not truncated else f", {name}"
            if current_len + len(part) + 1 > max_names_length:
                break
            truncated.append(name)
            current_len += len(part)
        names_text = ", ".join(truncated) + ", …"

    if names_text:
        return (
            f"Итоги за вчера:\n"
            f"✅ Выполнили практику {len(done)} из {total} участников: {names_text}"
        )
    return (
        f"Итоги за вчера:\n"
        f"✅ Выполнили практику 0 из {total} участников"
    )


def _format_intermediate_section(progress_rows: list[ProgressRow]) -> str:
    lines = ["Промежуточные итоги челленджа:"]
    for row in progress_rows:
        name = display_name(row.participant.user_nickname, row.participant.user_name)
        lines.append(f"• {name} — {row.completed}/{row.total} дней")
    return "\n".join(lines)


def _format_final_section(final_rows: list[FinalRankRow]) -> str:
    lines = ["Поздравляю с окончанием челленджа!", "Итоги:"]
    for row in final_rows:
        name = display_name(row.participant.user_nickname, row.participant.user_name)
        lines.append(f"• {name} — {row.completed}/{row.total} дней — {row.label}")
    return "\n".join(lines)


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


def build_summary_message(
    kind: SummaryKind,
    participants: list[ChallengeParticipant],
    yesterday_done_ids: set[int],
    progress_rows: Optional[list[ProgressRow]] = None,
    final_rows: Optional[list[FinalRankRow]] = None,
) -> str:
    """Собирает текст утренней сводки по типу."""
    header = "Доброе утро, йоги ☀️"
    parts = [header]

    if kind in ("daily", "intermediate"):
        parts.append(_format_yesterday_section(participants, yesterday_done_ids))

    if kind == "intermediate" and progress_rows is not None:
        parts.append(_format_intermediate_section(progress_rows))

    if kind == "final" and final_rows is not None:
        parts.append(_format_final_section(final_rows))

    text = "\n".join(parts)
    if len(text) > TELEGRAM_MESSAGE_LIMIT:
        text = text[: TELEGRAM_MESSAGE_LIMIT - 1] + "…"
    return text


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
        progress_rows = build_progress_rows(participants, completed_by_user_id)
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
