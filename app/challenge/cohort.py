"""Календарный поток челленджа (cohort): день 1–29 от CHALLENGE_START_DATE + константы."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import (
    CHALLENGE_START_DATE,
    CHALLENGE_START_PRACTICE_ID,
    DEFAULT_TZ,
)

# Длительность и контрольные дни потока
CHALLENGE_DURATION = 28
INTERMEDIATE_DAYS = frozenset({8, 15, 22})
FINAL_SUMMARY_DAY = 29

# Утренняя сводка в группе
SUMMARY_HOUR = 10
SUMMARY_MINUTE = 10

# Воскресное расписание в группе
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

MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)


def _today_moscow(for_date: Optional[date] = None) -> date:
    if for_date is not None:
        return for_date
    return datetime.now(MOSCOW_TZ).date()


def get_challenge_start_date() -> Optional[date]:
    """Парсит CHALLENGE_START_DATE (YYYY-MM-DD) или None."""
    raw = (CHALLENGE_START_DATE or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def get_challenge_start_practice_id() -> Optional[int]:
    """Парсит CHALLENGE_START_PRACTICE_ID или None."""
    raw = (CHALLENGE_START_PRACTICE_ID or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 1 else None


def is_cohort_configured() -> bool:
    """Обе env заданы и валидны."""
    return get_challenge_start_date() is not None and get_challenge_start_practice_id() is not None


def get_cohort_challenge_day(for_date: Optional[date] = None) -> int:
    """День потока: 0 до старта; 1 в день старта; … 28; 29 = финал."""
    start = get_challenge_start_date()
    if start is None:
        return 0
    today = _today_moscow(for_date)
    if today < start:
        return 0
    return (today - start).days + 1


def get_first_send_date_for_enrollment(for_date: Optional[date] = None) -> date:
    """Первая дата рассылки после записи в поток.

    До старта — день старта; в день старта и позже — сегодня
    (практика уходит сегодня: в notify_time или сразу, если время уже прошло).
    """
    start = get_challenge_start_date()
    today = _today_moscow(for_date)
    if start is None:
        return today + timedelta(days=1)
    if today < start:
        return start
    return today


def get_upcoming_week_day_range(cohort_day: int) -> Optional[tuple[int, int]]:
    """Диапазон дней потока на ближайшую неделю (вс 20:00).

    В воскресенье перед стартом cohort_day=0 → дни 1–7.
    В воскресенье после дня 7 → 8–14 и т.д.
    """
    if cohort_day >= CHALLENGE_DURATION:
        return None
    from_day = cohort_day + 1
    if from_day > CHALLENGE_DURATION:
        return None
    to_day = min(cohort_day + 7, CHALLENGE_DURATION)
    return from_day, to_day


def challenge_day_weekday_label(challenge_day: int) -> str:
    """Название дня недели от даты старта потока (день 1 = weekday старта)."""
    start = get_challenge_start_date()
    if start is None:
        return WEEKDAY_FULL_LABELS[(challenge_day - 1) % 7]
    weekday = (start.weekday() + challenge_day - 1) % 7
    return WEEKDAY_FULL_LABELS[weekday]


def enrollment_closed_message() -> str:
    """Текст пользователю, если поток не настроен (без технических деталей env)."""
    return (
        "Запись в текущий поток челленджа сейчас закрыта.\n"
        "Если нужна помощь — напиши админу."
    )


def cohort_not_configured_message() -> str:
    return (
        "Поток челленджа не настроен: задай CHALLENGE_START_DATE и "
        "CHALLENGE_START_PRACTICE_ID в окружении."
    )
