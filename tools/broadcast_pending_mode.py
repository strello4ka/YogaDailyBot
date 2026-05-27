"""Разовая рассылка пользователям с bot_mode = pending (не выбрали режим после /start).

Не запускается при деплое. Сначала dry-run, затем отправка с --send --confirm SEND.

Подготовка:
  1) tools/broadcast.env.example → tools/.env.broadcast (DATABASE_URL, BOT_TOKEN)
  2) python3 tools/broadcast_pending_mode.py
  3) python3 tools/broadcast_pending_mode.py --send --confirm SEND

Тест одному пользователю:
  python3 tools/broadcast_pending_mode.py --user-id 123456 --send --confirm SEND
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
import psycopg2
from psycopg2.extras import RealDictCursor

# Текст как в app/onboarding.py (напоминание через 1 ч)
PENDING_MODE_MESSAGE = (
    "Чтобы бот начал работать, тебе нужно выбрать режим. \n\n"
    "Жми *Выбрать режим*: Daily или By mood — и погнали 🧡"
)


def _load_env_files() -> None:
    """Сначала корневой .env, затем tools/.env.broadcast с приоритетом (override=True)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve().parent
    root = here.parent
    root_env = root / ".env"
    if root_env.is_file():
        load_dotenv(root_env, override=False)
    for path in (here / ".env.broadcast", root / ".env.broadcast"):
        if path.is_file():
            load_dotenv(path, override=True)


def print_bot_identity(token: str) -> bool:
    """Показывает @username бота по токену (чтобы проверить, не старый ли бот)."""
    try:
        response = httpx.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        if response.status_code != 200:
            print("Не удалось проверить токен (getMe).", file=sys.stderr)
            return False
        bot = response.json().get("result") or {}
        username = bot.get("username") or "?"
        print(f"Токен относится к боту: @{username} (id={bot.get('id')})")
        return True
    except httpx.HTTPError as e:
        print(f"Ошибка проверки токена: {e}", file=sys.stderr)
        return False


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
            "Задайте DATABASE_URL или переменные PostgreSQL. Не хватает: " + ", ".join(missing)
        )

    return (
        f"postgresql://{required['POSTGRESQL_USER']}:{required['POSTGRESQL_PASSWORD']}"
        f"@{required['POSTGRESQL_HOST']}:{required['POSTGRESQL_PORT']}"
        f"/{required['POSTGRESQL_DBNAME']}?sslmode=require"
    )


def assert_database_url_not_placeholder(database_url: str) -> None:
    parsed = urlparse(database_url)
    host = (parsed.hostname or "").lower()
    user = (parsed.username or "").lower()
    password = (parsed.password or "").lower()
    db_tail = (parsed.path or "").strip("/").lower()

    if host == "host":
        raise RuntimeError(
            "В DATABASE_URL указан заглушечный хост «HOST». Скопируйте реальный DATABASE_URL "
            "(или DATABASE_PUBLIC_URL с Railway) в tools/.env.broadcast."
        )
    if user == "user" and password == "password":
        raise RuntimeError("В DATABASE_URL остались заглушки user:password из примера.")
    if db_tail == "dbname":
        raise RuntimeError("В DATABASE_URL осталось имя базы «dbname» из примера.")
    if ".railway.internal" in (database_url or "").lower():
        raise RuntimeError(
            "В DATABASE_URL внутренний адрес *.railway.internal — с Mac не подключится. "
            "Используйте DATABASE_PUBLIC_URL из Railway как DATABASE_URL."
        )


def load_pending_recipients(
    conn, user_id: Optional[int], limit: Optional[int]
) -> list[dict]:
    """Пользователи без выбранного режима (bot_mode = pending), не заблокировали бота."""
    query = """
        SELECT user_id, chat_id, user_name, user_nickname
        FROM users
        WHERE COALESCE(bot_mode, 'pending') = 'pending'
          AND COALESCE(is_blocked, FALSE) = FALSE
          AND chat_id IS NOT NULL
    """
    params: list[Any] = []
    if user_id:
        query += " AND user_id = %s"
        params.append(user_id)
    query += " ORDER BY user_id"
    if limit:
        query += " LIMIT %s"
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
        body = response.json()
        return False, body.get("description", response.text)
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
        description="Разовая рассылка: выбрать режим (bot_mode = pending).",
        epilog="Dry-run: python3 tools/broadcast_pending_mode.py\n"
        "Отправка: python3 tools/broadcast_pending_mode.py --send --confirm SEND",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--send", action="store_true", help="Реально отправить сообщения.")
    parser.add_argument(
        "--confirm",
        default="",
        help='Обязательно с --send: ровно "SEND".',
    )
    parser.add_argument("--limit", type=int, help="Лимит получателей (для теста).")
    parser.add_argument("--user-id", type=int, help="Один user_id для теста.")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("broadcast_reports")
        / f"pending_mode_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
        help="Путь к CSV-отчёту.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Пауза между запросами к Telegram (сек).",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Токен бота (иначе BOT_TOKEN из окружения / .env).",
    )
    parser.add_argument(
        "--plain-text",
        action="store_true",
        help="Без Markdown (если меняете текст и в нём спецсимволы).",
    )
    return parser.parse_args()


def main() -> int:
    _load_env_files()
    args = parse_args()

    if args.send and args.confirm != "SEND":
        print('Отказ: для отправки нужны --send и --confirm SEND.', file=sys.stderr)
        return 2

    token = (args.token or "").strip() or os.getenv("BOT_TOKEN")
    if args.send and not token:
        print(
            "Отказ: задайте BOT_TOKEN в tools/.env.broadcast или флаг --token.",
            file=sys.stderr,
        )
        return 2

    if token:
        print_bot_identity(token)
        if (args.token or "").strip():
            print("Источник токена: флаг --token")
        elif (Path(__file__).resolve().parent / ".env.broadcast").is_file():
            print("Источник токена: tools/.env.broadcast (перекрывает BOT_TOKEN из корневого .env)")

    parse_mode: Optional[str] = None if args.plain_text else "Markdown"

    dsn = get_database_url()
    assert_database_url_not_placeholder(dsn)

    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        recipients = load_pending_recipients(conn, args.user_id, args.limit)
    finally:
        conn.close()

    print(f"Получателей (bot_mode=pending, не blocked): {len(recipients)}")
    if recipients and not args.send:
        print("Превью текста:")
        print(PENDING_MODE_MESSAGE)

    report_rows: list[dict] = []
    if not args.send:
        for recipient in recipients:
            report_rows.append({**recipient, "status": "dry_run", "details": "not sent"})
        write_report(report_rows, args.report)
        print(f"Dry-run отчёт: {args.report}")
        return 0

    assert token is not None
    with httpx.Client() as client:
        for recipient in recipients:
            ok, details = send_message(
                client,
                token,
                recipient["chat_id"],
                PENDING_MODE_MESSAGE,
                parse_mode=parse_mode,
            )
            status = "sent" if ok else "failed"
            report_rows.append({**recipient, "status": status, "details": details})
            print(f"{recipient['user_id']}: {status} ({details})")
            time.sleep(args.sleep)

    write_report(report_rows, args.report)
    sent = sum(1 for row in report_rows if row["status"] == "sent")
    failed = len(report_rows) - sent
    print(f"Готово. Отправлено: {sent}, ошибок: {failed}. Отчёт: {args.report}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
