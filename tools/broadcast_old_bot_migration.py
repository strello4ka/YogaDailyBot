"""One-time migration notice broadcast via the old Telegram bot token.

This script is intentionally manual. It does not run during Railway deploys.
Use dry-run first, then send with an explicit confirmation flag.

Подготовка без ручных export:
  1) Скопируйте tools/broadcast.env.example -> tools/.env.broadcast
  2) Заполните DATABASE_URL и (для отправки) OLD_BOT_TOKEN
  3) При необходимости задайте ARCHIVE_SUFFIX — иначе суффикс берётся из archive.migration_log
  4) Запуск: python3 tools/broadcast_old_bot_migration.py
     затем: python3 tools/broadcast_old_bot_migration.py --send --confirm SEND
"""

import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


def _load_env_files() -> None:
    """Подхватывает .env из корня проекта и tools/.env.broadcast (не перетирает уже выставленные export)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve().parent
    root = here.parent
    for path in (root / ".env", here / ".env.broadcast", root / ".env.broadcast"):
        if path.is_file():
            load_dotenv(path, override=False)


_ARCHIVE_SUFFIX_RE = re.compile(r"^[\w-]+$")


def _validate_archive_suffix(suffix: str) -> str:
    if not _ARCHIVE_SUFFIX_RE.match(suffix):
        raise ValueError(
            "Недопустимый --archive-suffix: допустимы только буквы, цифры, подчёркивание и дефис."
        )
    return suffix


DEFAULT_MESSAGE = """Привет!
Я переехал заграницу и стал стабильнее.
*Вот мой новый адрес:* @YogaDailyBot
Переходи и жми start, очень жду тебя!

А еще у меня *появился новый режим By mood*, который многие хотели: теперь практики можно получать по настроению в моменте.
Выбираешь нужную кнопку: «Ленивые дни», «Без коврика», «Практика дня»...и я сразу скидываю видео под твой запрос. Также можно самому настроить время и интенсивность.
Идем скорее тестировать!

И это еще не все новости..У нас *стартует 4-ый поток челленджа*, который все уже заждались!
*18 мая старт*
[Подробное описание правил тут](https://t.me/yogastrello4ka/575)
Если готов присоединиться, пиши @helentajj

Спасибо, что остаешься со мной 🧡"""


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    required = {
        "POSTGRESQL_HOST": os.getenv("POSTGRESQL_HOST"),
        "POSTGRESQL_PORT": os.getenv("POSTGRESQL_PORT", "5432"),
        "POSTGRESQL_USER": os.getenv("POSTGRESQL_USER"),
        "POSTGRESQL_PASSWORD": os.getenv("POSTGRESQL_PASSWORD"),
        "POSTGRESQL_DBNAME": os.getenv("POSTGRESQL_DBNAME"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Set DATABASE_URL or PostgreSQL variables first. Missing: "
            + ", ".join(missing)
        )

    return (
        f"postgresql://{required['POSTGRESQL_USER']}:{required['POSTGRESQL_PASSWORD']}"
        f"@{required['POSTGRESQL_HOST']}:{required['POSTGRESQL_PORT']}"
        f"/{required['POSTGRESQL_DBNAME']}?sslmode=require"
    )


def assert_database_url_not_placeholder(database_url: str) -> None:
    """Если в .env остался текст из примера (USER, HOST, DBNAME) — сразу понятная ошибка."""
    parsed = urlparse(database_url)
    host = (parsed.hostname or "").lower()
    user = (parsed.username or "").lower()
    password = (parsed.password or "").lower()
    db_tail = (parsed.path or "").strip("/").lower()

    if host == "host":
        raise RuntimeError(
            "В DATABASE_URL указан заглушечный хост «HOST» (как в файле-примере).\n"
            "Нужно вставить реальную строку целиком из Railway:\n"
            "  Postgres-сервис → вкладка Variables (или Connect) → скопировать DATABASE_URL.\n"
            "Это длинная строка вида postgresql://…@что-то.railway.app:порт/railway"
        )
    if user == "user" and password == "password":
        raise RuntimeError(
            "В DATABASE_URL остались заглушки user:password из примера.\n"
            "Скопируйте настоящий DATABASE_URL из Railway (см. выше)."
        )
    if db_tail == "dbname":
        raise RuntimeError(
            "В DATABASE_URL осталось имя базы «dbname» из примера.\n"
            "Скопируйте настоящий DATABASE_URL из Railway целиком."
        )
    if host.endswith(".railway.internal") or ".railway.internal" in (database_url or "").lower():
        raise RuntimeError(
            "В DATABASE_URL указан внутренний адрес Railway (*.railway.internal).\n"
            "С вашего Mac он не подключается — такую строку видит только сервис внутри Railway.\n\n"
            "Что сделать: Railway → ваш сервис PostgreSQL → вкладка Variables → скопировать "
            "DATABASE_PUBLIC_URL (внешнее подключение через TCP Proxy) и вставить в tools/.env.broadcast "
            "вместо текущей строки как DATABASE_URL=...\n\n"
            "Если переменной DATABASE_PUBLIC_URL нет: в настройках Postgres включите публичный доступ / TCP Proxy "
            "(в документации Railway это отдельный внешний хост и порт).\n\n"
            "Обходной путь: один раз запустить этот скрипт на Railway (там внутренний DATABASE_URL сработает)."
        )


def get_latest_archive_suffix(conn) -> str:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT suffix
            FROM archive.migration_log
            WHERE action = 'archive_user_data_and_reset_working_tables'
            ORDER BY archived_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
    if not row:
        raise RuntimeError("No archived user migration found in archive.migration_log.")
    return row[0]


def load_recipients(conn, suffix: str, user_id: Optional[int], limit: Optional[int]) -> list[dict]:
    table_name = f"users_{suffix}"
    query = sql.SQL(
        """
        SELECT user_id, chat_id, user_name, user_nickname
        FROM archive.{table}
        WHERE COALESCE(is_blocked, FALSE) = FALSE
        {user_filter}
        ORDER BY user_id
        {limit_clause}
        """
    ).format(
        table=sql.Identifier(table_name),
        user_filter=sql.SQL("AND user_id = %s") if user_id else sql.SQL(""),
        limit_clause=sql.SQL("LIMIT %s") if limit else sql.SQL(""),
    )

    params: list[int] = []
    if user_id:
        params.append(user_id)
    if limit:
        params.append(limit)

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def send_message(
    client: httpx.Client,
    token: str,
    chat_id: int,
    text: str,
    *,
    parse_mode: Optional[str] = "Markdown",
) -> tuple[bool, str]:
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    response = client.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json=payload,
        timeout=20,
    )
    if response.status_code == 200:
        return True, "ok"
    try:
        payload = response.json()
        return False, payload.get("description", response.text)
    except ValueError:
        return False, response.text


def write_report(rows: list[dict], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "user_id",
                "chat_id",
                "user_name",
                "user_nickname",
                "status",
                "details",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Broadcast migration notice to archived users via old bot token.",
        epilog="Пример: python3 tools/broadcast_old_bot_migration.py\n"
        "Отправка: python3 tools/broadcast_old_bot_migration.py --send --confirm SEND\n"
        "Переменные: см. tools/broadcast.env.example (файл tools/.env.broadcast).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--send", action="store_true", help="Actually send messages.")
    parser.add_argument(
        "--confirm",
        default="",
        help='Required with --send. Must be exactly "SEND".',
    )
    parser.add_argument("--limit", type=int, help="Limit recipients for test sends.")
    parser.add_argument("--user-id", type=int, help="Send/dry-run for one Telegram user_id.")
    parser.add_argument(
        "--message-file",
        type=Path,
        help="Optional UTF-8 text file with custom message.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("broadcast_reports") / f"old_bot_migration_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
        help="CSV report path.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Delay between Telegram requests in seconds.",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Токен старого бота (иначе переменная OLD_BOT_TOKEN из окружения / .env).",
    )
    parser.add_argument(
        "--archive-suffix",
        default="",
        help="Суффикс таблицы archive.users_<suffix>. Если не задан — последний из archive.migration_log.",
    )
    parser.add_argument(
        "--plain-text",
        action="store_true",
        help="Отключить Markdown (для своего текста из --message-file без разметки).",
    )
    return parser.parse_args()


def main() -> int:
    _load_env_files()
    args = parse_args()

    if args.send and args.confirm != "SEND":
        print('Refusing to send: pass --confirm SEND together with --send.', file=sys.stderr)
        return 2

    token = (args.token or "").strip() or os.getenv("OLD_BOT_TOKEN")
    if args.send and not token:
        print(
            "Refusing to send: задайте токен — переменная OLD_BOT_TOKEN в tools/.env.broadcast "
            "или флаг --token ...",
            file=sys.stderr,
        )
        return 2

    message = (
        args.message_file.read_text(encoding="utf-8")
        if args.message_file
        else DEFAULT_MESSAGE
    )

    parse_mode: Optional[str] = None if args.plain_text else "Markdown"

    dsn = get_database_url()
    assert_database_url_not_placeholder(dsn)

    try:
        conn = psycopg2.connect(dsn, connect_timeout=10)
    except psycopg2.OperationalError as e:
        err = str(e).lower()
        if "could not translate host name" in err and (
            "host" in err or "railway.internal" in err
        ):
            print(
                "Не удалось подключиться к базе: имя сервера из DATABASE_URL не находится в интернете.\n"
                "Часто так бывает, если в строке осталась заглушка HOST или внутренний адрес *.railway.internal "
                "при запуске скрипта с вашего компьютера.\n"
                "В Railway у Postgres возьмите переменную DATABASE_PUBLIC_URL (внешнее подключение) "
                "и подставьте её в tools/.env.broadcast как DATABASE_URL.\n",
                file=sys.stderr,
            )
        raise
    try:
        if (args.archive_suffix or "").strip():
            suffix = _validate_archive_suffix((args.archive_suffix or "").strip())
        else:
            env_suffix = (os.getenv("ARCHIVE_SUFFIX") or "").strip()
            suffix = _validate_archive_suffix(env_suffix) if env_suffix else get_latest_archive_suffix(conn)
        recipients = load_recipients(conn, suffix, args.user_id, args.limit)
    finally:
        conn.close()

    print(f"Archive suffix: {suffix}")
    print(f"Recipients: {len(recipients)}")

    report_rows: list[dict] = []
    if not args.send:
        for recipient in recipients:
            report_rows.append({**recipient, "status": "dry_run", "details": "not sent"})
        write_report(report_rows, args.report)
        print(f"Dry-run report: {args.report}")
        return 0

    assert token is not None
    with httpx.Client() as client:
        for recipient in recipients:
            ok, details = send_message(
                client, token, recipient["chat_id"], message, parse_mode=parse_mode
            )
            status = "sent" if ok else "failed"
            report_rows.append({**recipient, "status": status, "details": details})
            print(f"{recipient['user_id']}: {status} ({details})")
            time.sleep(args.sleep)

    write_report(report_rows, args.report)
    sent = sum(1 for row in report_rows if row["status"] == "sent")
    failed = len(report_rows) - sent
    print(f"Done. Sent: {sent}, failed: {failed}. Report: {args.report}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
