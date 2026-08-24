"""Каталог и конфигурация быстрых кнопок By mood / «Ещё практики»."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.config import QUICK_PRACTICE_FILTERS


Pool = Literal["yoga", "combined", "flow"]


@dataclass(frozen=True)
class QuickFilter:
    slug: str
    label: str
    filter_key: str
    where_sql: str = ""
    params: tuple = ()
    empty_message: str = "Не нашлось подходящей практики. Попробуй другой фильтр."
    pool: Pool = "combined"


QUICK_FILTERS: dict[str, QuickFilter] = {
    "lazy": QuickFilter(
        slug="lazy",
        label="Ленивые дни",
        filter_key="lazy",
        where_sql=(
            " AND LOWER(TRIM(COALESCE(yp.difficulty, ''))) = 'сверх низкая' "
            " AND yp.time_practices <= 30 AND yp.time_practices > 0 "
        ),
        empty_message="Не нашлось практик с очень низкой сложностью. Попробуй другой фильтр.",
    ),
    "no_mat": QuickFilter(
        slug="no_mat",
        label="Без коврика",
        filter_key="no_mat",
        where_sql=" AND yp.without_mat = TRUE ",
        empty_message=(
            "Пока нет практик с отметкой «без коврика» в базе. "
            "Как только добавим — фильтр заработает."
        ),
    ),
    "healthy_back": QuickFilter(
        slug="healthy_back",
        label="Здоровая спина",
        filter_key="healthy_back",
        where_sql=" AND %s = ANY(COALESCE(yp.teg, ARRAY[]::TEXT[])) ",
        params=("Здоровая спина",),
        empty_message="Не нашлось практик для здоровой спины. Попробуй другой фильтр.",
    ),
    "relax": QuickFilter(
        slug="relax",
        label="Расслабление",
        filter_key="relax",
        where_sql=" AND %s = ANY(COALESCE(yp.teg, ARRAY[]::TEXT[])) ",
        params=("Расслабление",),
        empty_message="Не нашлось расслабляющих практик. Попробуй другой фильтр.",
    ),
    "hard": QuickFilter(
        slug="hard",
        label="Хард",
        filter_key="hard",
        where_sql=(
            " AND LOWER(TRIM(COALESCE(yp.difficulty, ''))) = 'сверх высокая' "
            " AND yp.time_practices <= 30 AND yp.time_practices > 0 "
        ),
        empty_message="Не нашлось практик со сверх высокой сложностью. Попробуй другой фильтр.",
    ),
    "long": QuickFilter(
        slug="long",
        label="Длинные",
        filter_key="long",
        where_sql=" AND yp.time_practices > 45 ",
        empty_message="Не нашлось практик длиннее 45 минут. Попробуй другой фильтр.",
    ),
    "strello4ka": QuickFilter(
        slug="strello4ka",
        label="strello4ka",
        filter_key="strello4ka",
        where_sql=" AND LOWER(TRIM(COALESCE(yp.channel_name, ''))) LIKE %s ",
        params=("%strello4ka%",),
        empty_message="Не нашлось практик от strello4ka. Попробуй другой фильтр.",
    ),
    "five": QuickFilter(
        slug="five",
        label="Мини",
        filter_key="five",
        where_sql=" AND yp.time_practices <= 8 AND yp.time_practices > 0 ",
        empty_message=(
            "Не нашлось коротких практик до 8 минут включительно. Попробуй другой фильтр."
        ),
    ),
    "day": QuickFilter(
        slug="day",
        label="Практика дня",
        filter_key="day",
        empty_message=(
            "Сейчас не нашлось подходящей практики в базе. "
            "Попробуй чуть позже или другой фильтр."
        ),
        pool="yoga",
    ),
    "self": QuickFilter(
        slug="self",
        label="САМ решу",
        filter_key="self_start",
        pool="flow",
    ),
}


def get_active_quick_filters(raw_value: Optional[str] = None) -> tuple[QuickFilter, ...]:
    """Возвращает включённые кнопки в порядке из env, без повторов и опечаток."""
    raw = QUICK_PRACTICE_FILTERS if raw_value is None else raw_value
    result: list[QuickFilter] = []
    seen: set[str] = set()
    for value in raw.split(","):
        slug = value.strip().lower()
        if not slug or slug in seen or slug not in QUICK_FILTERS:
            continue
        seen.add(slug)
        result.append(QUICK_FILTERS[slug])
    if not result:
        result.append(QUICK_FILTERS["self"])
    return tuple(result)


def get_active_quick_filter_by_label(label: str) -> Optional[QuickFilter]:
    return next(
        (spec for spec in get_active_quick_filters() if spec.label == label),
        None,
    )


def get_quick_filter(slug: str) -> Optional[QuickFilter]:
    return QUICK_FILTERS.get(slug)


def record_quick_filter_click(
    user_id: int,
    spec: QuickFilter,
    surface: str,
    result_found: Optional[bool],
) -> None:
    from data.db import log_quick_filter_event

    log_quick_filter_event(user_id, spec.filter_key, surface, result_found)


async def select_and_deliver_quick_filter(
    context,
    user_id: int,
    chat_id: int,
    spec: QuickFilter,
    surface: str,
) -> str:
    """Возвращает sent / empty / failed и записывает факт нажатия."""
    from app.by_mood.send_utils import deliver_by_mood_practice
    from data.db import pick_random_by_mood_practice, pick_random_combined_mood_pool

    if spec.pool == "yoga":
        row = pick_random_by_mood_practice(
            user_id,
            spec.filter_key,
            spec.where_sql,
            spec.params,
        )
    else:
        row = pick_random_combined_mood_pool(
            user_id,
            spec.filter_key,
            spec.where_sql,
            spec.params,
        )

    record_quick_filter_click(user_id, spec, surface, row is not None)
    if row is None:
        return "empty"
    if not await deliver_by_mood_practice(
        context,
        chat_id,
        user_id,
        spec.filter_key,
        row,
    ):
        return "failed"
    return "sent"
