"""
Удаление ВСЕХ сообщений в Telegram-группе за период.

Период по умолчанию: 1 февраля 2026 — 1 апреля 2026 (включительно).

Важно:
- Работает от ВАШЕГО личного аккаунта (не от бота).
- Нужны права админа на удаление сообщений в группе.
- Сначала запускайте с DRY_RUN = True (только подсчёт, без удаления).

Как получить API_ID и API_HASH: https://my.telegram.org → API development tools
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from telethon import TelegramClient

# === ЗАПОЛНИТЕ ===
API_ID = 0  # число с my.telegram.org
API_HASH = "your_api_hash"  # строка с my.telegram.org

# Группа: @username или numeric id вида -1001234567890
CHAT = "@your_group_username"

# Период (UTC). 1 апреля включительно до конца дня.
DATE_FROM = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
DATE_TO = datetime(2026, 4, 1, 23, 59, 59, tzinfo=timezone.utc)

# True = только посчитать сообщения. False = реально удалить.
DRY_RUN = True

BATCH_SIZE = 100
PAUSE_SECONDS = 1.0


async def main() -> None:
    if not API_ID or API_HASH in ("", "your_api_hash"):
        raise SystemExit(
            "Заполните API_ID и API_HASH в начале файла "
            "(взять на https://my.telegram.org)."
        )
    if CHAT in ("", "@your_group_username"):
        raise SystemExit("Укажите CHAT: @username группы или её numeric id.")

    client = TelegramClient("delete_session", API_ID, API_HASH)
    await client.start()

    chat = await client.get_entity(CHAT)
    title = getattr(chat, "title", CHAT)
    print(f"Чат: {title}")
    print(f"Период: {DATE_FROM.date()} … {DATE_TO.date()} (UTC)")
    print(f"Режим: {'ПРОСМОТР (удаления нет)' if DRY_RUN else 'УДАЛЕНИЕ'}")

    ids: list[int] = []
    async for msg in client.iter_messages(chat, offset_date=DATE_TO):
        if msg.date is None:
            continue
        msg_date = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)

        if msg_date > DATE_TO:
            continue
        if msg_date < DATE_FROM:
            break

        ids.append(msg.id)

    print(f"Найдено сообщений: {len(ids)}")

    if DRY_RUN:
        print(
            "DRY_RUN=True — ничего не удалено. "
            "Если число верное, поставьте DRY_RUN=False и запустите снова."
        )
        await client.disconnect()
        return

    if not ids:
        print("Нечего удалять.")
        await client.disconnect()
        return

    deleted = 0
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i : i + BATCH_SIZE]
        await client.delete_messages(chat, batch, revoke=True)
        deleted += len(batch)
        print(f"Удалено: {deleted}/{len(ids)}")
        await asyncio.sleep(PAUSE_SECONDS)

    print("Готово.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
