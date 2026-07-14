"""Идентификация практики: yoga_practices vs mood_practices."""

from __future__ import annotations

from typing import Optional, Tuple

from data.db import PRACTICE_CATALOG_MOOD, PRACTICE_CATALOG_YOGA


def format_practice_callback(prefix: str, practice_id: int, practice_catalog: str = PRACTICE_CATALOG_YOGA) -> str:
    """callback_data вида fav_toggle:yoga:42."""
    return f"{prefix}:{practice_catalog}:{practice_id}"


def parse_practice_callback(data: str, prefix: str) -> Tuple[Optional[int], str]:
    """Разбор callback_data. Старый формат prefix:42 трактуем как yoga."""
    if not data.startswith(f"{prefix}:"):
        return None, PRACTICE_CATALOG_YOGA
    rest = data[len(prefix) + 1 :]
    parts = rest.split(":", 1)
    if len(parts) == 1:
        try:
            return int(parts[0]), PRACTICE_CATALOG_YOGA
        except ValueError:
            return None, PRACTICE_CATALOG_YOGA
    catalog, pid_str = parts[0], parts[1]
    if catalog not in (PRACTICE_CATALOG_YOGA, PRACTICE_CATALOG_MOOD):
        try:
            return int(parts[0]), PRACTICE_CATALOG_YOGA
        except ValueError:
            return None, PRACTICE_CATALOG_YOGA
    try:
        return int(pid_str), catalog
    except ValueError:
        return None, PRACTICE_CATALOG_YOGA


def practice_id_from_callback_data(data: str) -> Optional[int]:
    for prefix in ("fav_toggle", "practice_done"):
        if data.startswith(f"{prefix}:"):
            pid, _ = parse_practice_callback(data, prefix)
            return pid
    return None


def practice_catalog_from_callback_data(data: str) -> str:
    for prefix in ("fav_toggle", "practice_done"):
        if data.startswith(f"{prefix}:"):
            _, catalog = parse_practice_callback(data, prefix)
            return catalog
    return PRACTICE_CATALOG_YOGA


def practice_catalog_from_action_markup(reply_markup) -> str:
    if not reply_markup or not reply_markup.inline_keyboard:
        return PRACTICE_CATALOG_YOGA
    for row in reply_markup.inline_keyboard:
        for btn in row:
            data = btn.callback_data or ""
            if data.startswith(("fav_toggle:", "practice_done:")):
                return practice_catalog_from_callback_data(data)
    return PRACTICE_CATALOG_YOGA
