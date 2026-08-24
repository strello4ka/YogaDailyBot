"""Безопасная разовая миграция поля ``teg`` для практик.

По умолчанию скрипт выполняет только read-only проверку payload и записей в БД.
Изменения выполняются исключительно с двумя явными флагами::

    python3 tools/migrate_practice_teg.py --apply --confirm APPLY_TEG

Перед фактическим запуском на production требуется отдельное подтверждение владельца.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:  # Payload можно валидировать без PostgreSQL-драйвера.
    psycopg2 = None
    sql = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_PAYLOAD_PATH = (
    PROJECT_ROOT / "data" / "migrations" / "20260824_practice_teg.json"
)
CONFIRMATION = "APPLY_TEG"
TABLES = {
    "yoga": ("yoga_practices", "practices_id"),
    "mood": ("mood_practices", "mood_practice_id"),
}


@dataclass(frozen=True)
class PracticeTeg:
    catalog: str
    practice_id: int
    title: str
    teg: tuple[str, ...]


@dataclass(frozen=True)
class MigrationPayload:
    allowed_teg: frozenset[str]
    expected: dict[str, int]
    practices: tuple[PracticeTeg, ...]


def load_payload(path: Path) -> MigrationPayload:
    """Загружает payload и отклоняет неполные или неоднозначные данные."""
    with path.open(encoding="utf-8") as file:
        raw = json.load(file)

    if raw.get("version") != 1 or raw.get("field") != "teg":
        raise ValueError("Ожидался payload version=1 для поля teg")

    allowed = frozenset(raw.get("allowed_teg") or [])
    expected = raw.get("expected") or {}
    if not allowed:
        raise ValueError("allowed_teg не должен быть пустым")

    practices: list[PracticeTeg] = []
    seen: set[tuple[str, int]] = set()
    for item in raw.get("practices") or []:
        catalog = item.get("catalog")
        practice_id = item.get("practice_id")
        title = item.get("title")
        teg = tuple(item.get("teg") or [])

        if catalog not in TABLES:
            raise ValueError(f"Неизвестный каталог: {catalog!r}")
        if not isinstance(practice_id, int) or practice_id <= 0:
            raise ValueError(f"Некорректный practice_id: {practice_id!r}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Пустое название у {catalog}:{practice_id}")
        if not teg:
            raise ValueError(f"Пустой teg у {catalog}:{practice_id}")
        if len(teg) != len(set(teg)):
            raise ValueError(f"Повтор teg у {catalog}:{practice_id}: {teg}")
        unknown = set(teg) - allowed
        if unknown:
            raise ValueError(
                f"Неизвестный teg у {catalog}:{practice_id}: {sorted(unknown)}"
            )

        key = (catalog, practice_id)
        if key in seen:
            raise ValueError(f"Повтор catalog + practice_id: {catalog}:{practice_id}")
        seen.add(key)
        practices.append(
            PracticeTeg(
                catalog=catalog,
                practice_id=practice_id,
                title=title,
                teg=teg,
            )
        )

    actual = Counter(item.catalog for item in practices)
    if len(practices) != expected.get("total"):
        raise ValueError(
            f"Ожидалось {expected.get('total')} практик, получено {len(practices)}"
        )
    for catalog in TABLES:
        if actual[catalog] != expected.get(catalog):
            raise ValueError(
                f"Ожидалось {expected.get(catalog)} записей {catalog}, "
                f"получено {actual[catalog]}"
            )

    return MigrationPayload(
        allowed_teg=allowed,
        expected={key: int(value) for key, value in expected.items()},
        practices=tuple(practices),
    )


def group_by_catalog(
    practices: Iterable[PracticeTeg],
) -> dict[str, list[PracticeTeg]]:
    grouped = {catalog: [] for catalog in TABLES}
    for practice in practices:
        grouped[practice.catalog].append(practice)
    return grouped


def normalize_title(title: str) -> str:
    """Убирает незначащие пробелы по краям для защитной сверки названий."""
    return title.strip()


def column_exists(cursor: Any, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def fetch_practices(
    cursor: Any,
    catalog: str,
    practices: list[PracticeTeg],
    *,
    include_teg: bool,
) -> dict[int, dict[str, Any]]:
    table_name, id_column = TABLES[catalog]
    selected_columns = [sql.Identifier(id_column), sql.Identifier("title")]
    if include_teg:
        selected_columns.append(sql.Identifier("teg"))

    query = sql.SQL("SELECT {columns} FROM {table} WHERE {id_column} = ANY(%s)").format(
        columns=sql.SQL(", ").join(selected_columns),
        table=sql.Identifier(table_name),
        id_column=sql.Identifier(id_column),
    )
    cursor.execute(query, ([practice.practice_id for practice in practices],))

    result: dict[int, dict[str, Any]] = {}
    for row in cursor.fetchall():
        result[row[0]] = {
            "title": row[1],
            "teg": tuple(row[2] or ()) if include_teg else (),
        }
    return result


def validate_database_rows(
    cursor: Any,
    payload: MigrationPayload,
    *,
    allow_title_mismatch: bool,
    allow_overwrite: bool,
) -> None:
    """Проверяет ID, названия и существующие значения до записи."""
    grouped = group_by_catalog(payload.practices)
    problems: list[str] = []

    for catalog, practices in grouped.items():
        table_name, _ = TABLES[catalog]
        has_teg = column_exists(cursor, table_name, "teg")
        existing = fetch_practices(
            cursor,
            catalog,
            practices,
            include_teg=has_teg,
        )

        missing = sorted(
            practice.practice_id
            for practice in practices
            if practice.practice_id not in existing
        )
        if missing:
            problems.append(f"{catalog}: отсутствуют ID {missing}")

        for practice in practices:
            row = existing.get(practice.practice_id)
            if not row:
                continue
            if (
                normalize_title(row["title"]) != normalize_title(practice.title)
                and not allow_title_mismatch
            ):
                problems.append(
                    f"{catalog}:{practice.practice_id}: название в БД не совпадает "
                    f"с payload ({row['title']!r} != {practice.title!r})"
                )
            current_teg = tuple(row["teg"] or ())
            if (
                current_teg
                and current_teg != practice.teg
                and not allow_overwrite
            ):
                problems.append(
                    f"{catalog}:{practice.practice_id}: существующий teg "
                    f"{current_teg} отличается от {practice.teg}"
                )

    if problems:
        preview = "\n".join(f"- {problem}" for problem in problems[:30])
        suffix = "\n- …" if len(problems) > 30 else ""
        raise RuntimeError(f"Предварительная проверка не пройдена:\n{preview}{suffix}")


def add_schema(cursor: Any) -> None:
    """Добавляет idempotent-схему для массивов teg и GIN-индексы."""
    for catalog, (table_name, _) in TABLES.items():
        cursor.execute(
            sql.SQL(
                "ALTER TABLE {table} "
                "ADD COLUMN IF NOT EXISTS teg TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]"
            ).format(table=sql.Identifier(table_name))
        )
        cursor.execute(
            sql.SQL(
                "CREATE INDEX IF NOT EXISTS {index} "
                "ON {table} USING GIN (teg)"
            ).format(
                index=sql.Identifier(f"idx_{table_name}_teg"),
                table=sql.Identifier(table_name),
            )
        )
        print(f"   Схема teg подготовлена: {catalog} ({table_name})")


def update_rows(cursor: Any, payload: MigrationPayload) -> None:
    grouped = group_by_catalog(payload.practices)
    for catalog, practices in grouped.items():
        table_name, id_column = TABLES[catalog]
        query = sql.SQL(
            "UPDATE {table} SET teg = %s WHERE {id_column} = %s"
        ).format(
            table=sql.Identifier(table_name),
            id_column=sql.Identifier(id_column),
        )
        cursor.executemany(
            query,
            [(list(practice.teg), practice.practice_id) for practice in practices],
        )
        print(f"   Подготовлено обновлений {catalog}: {len(practices)}")


def verify_written_rows(cursor: Any, payload: MigrationPayload) -> None:
    grouped = group_by_catalog(payload.practices)
    mismatches: list[str] = []
    for catalog, practices in grouped.items():
        existing = fetch_practices(cursor, catalog, practices, include_teg=True)
        for practice in practices:
            actual = tuple(existing.get(practice.practice_id, {}).get("teg") or ())
            if actual != practice.teg:
                mismatches.append(
                    f"{catalog}:{practice.practice_id}: {actual} != {practice.teg}"
                )
    if mismatches:
        raise RuntimeError(
            "Проверка записанных teg не пройдена:\n"
            + "\n".join(f"- {item}" for item in mismatches[:30])
        )


def print_payload_summary(payload: MigrationPayload) -> None:
    catalog_counts = Counter(item.catalog for item in payload.practices)
    teg_counts = Counter(tag for item in payload.practices for tag in item.teg)
    print("Payload проверен:")
    print(f"   Всего практик: {len(payload.practices)}")
    print(f"   yoga: {catalog_counts['yoga']}; mood: {catalog_counts['mood']}")
    print("   Покрытие teg:")
    for tag in sorted(payload.allowed_teg):
        print(f"      {tag}: {teg_counts[tag]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Проверка и миграция поля teg для yoga_practices и mood_practices."
    )
    parser.add_argument(
        "--payload",
        type=Path,
        default=DEFAULT_PAYLOAD_PATH,
        help="Путь к JSON payload.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Разрешить DDL и заполнение teg. Без флага выполняется только проверка.",
    )
    parser.add_argument(
        "--payload-only",
        action="store_true",
        help="Проверить только JSON payload, не подключаясь к базе данных.",
    )
    parser.add_argument(
        "--confirm",
        help=f"Для --apply требуется точное значение {CONFIRMATION}.",
    )
    parser.add_argument(
        "--allow-title-mismatch",
        action="store_true",
        help="Не останавливать миграцию при изменившихся названиях (ID всё равно проверяются).",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Разрешить перезапись уже заполненных и отличающихся teg.",
    )
    return parser.parse_args()


def validate_apply_confirmation(apply: bool, confirmation: Optional[str]) -> None:
    if apply and confirmation != CONFIRMATION:
        raise ValueError(
            f"Для изменения базы требуется --confirm {CONFIRMATION}."
        )


def main() -> int:
    args = parse_args()
    payload = load_payload(args.payload)
    print_payload_summary(payload)

    validate_apply_confirmation(args.apply, args.confirm)
    if args.payload_only:
        if args.apply:
            raise ValueError("Флаги --payload-only и --apply нельзя использовать вместе.")
        print("PAYLOAD ONLY: подключение к базе данных не выполнялось.")
        return 0

    if psycopg2 is None:
        raise RuntimeError(
            "Для проверки БД нужен psycopg2. Установите зависимости проекта."
        )

    from app.config import get_db_config

    conn = psycopg2.connect(**get_db_config())
    try:
        with conn.cursor() as cursor:
            validate_database_rows(
                cursor,
                payload,
                allow_title_mismatch=args.allow_title_mismatch,
                allow_overwrite=args.allow_overwrite,
            )
            print(
                "Предварительная проверка БД пройдена: "
                f"все {len(payload.practices)} ID найдены."
            )

            if not args.apply:
                conn.rollback()
                print("CHECK ONLY: изменения схемы и данных не выполнялись.")
                return 0

            add_schema(cursor)
            update_rows(cursor, payload)
            verify_written_rows(cursor, payload)
        conn.commit()
        print("Миграция teg выполнена и проверена.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
