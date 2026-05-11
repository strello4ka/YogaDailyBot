"""One-time migration notice broadcast via the old Telegram bot token.

This script is intentionally manual. It does not run during Railway deploys.
Use dry-run first, then send with an explicit confirmation flag.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


DEFAULT_MESSAGE = """Привет!

YogaDailyBot переехал заграницу и стал стабильнее.
Вот мой новый адрес @YogaDailyBot
Приходи скорее и жми /start, очень жду тебя

Спасибо, что остаешься со мной, впереди много интересного"""


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


def send_message(client: httpx.Client, token: str, chat_id: int, text: str) -> tuple[bool, str]:
    response = client.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        },
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
        description="Broadcast migration notice to archived users via old bot token."
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.send and args.confirm != "SEND":
        print('Refusing to send: pass --confirm SEND together with --send.', file=sys.stderr)
        return 2

    token = os.getenv("OLD_BOT_TOKEN")
    if args.send and not token:
        print("Refusing to send: OLD_BOT_TOKEN is not set.", file=sys.stderr)
        return 2

    message = (
        args.message_file.read_text(encoding="utf-8")
        if args.message_file
        else DEFAULT_MESSAGE
    )

    conn = psycopg2.connect(get_database_url(), connect_timeout=10)
    try:
        suffix = get_latest_archive_suffix(conn)
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
            ok, details = send_message(client, token, recipient["chat_id"], message)
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
