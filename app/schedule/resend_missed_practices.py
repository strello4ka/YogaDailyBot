"""Скрипт для ручной доотправки практик пользователям, которые сегодня ещё не получили практику,
но их время уведомлений уже наступило.

Логика полностью повторяет обычную ежедневную рассылку:
- учитывается режим челленджа;
- обновляются program_position и user_days;
- логируется отправка в practice_logs;
- отправляются бонусные практики.

Использование (в проде через kubectl exec, пример):
    python -m app.schedule.resend_missed_practices
"""

import asyncio
import logging
from types import SimpleNamespace
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram.ext import Application

from app.config import BOT_TOKEN, DEFAULT_TZ
from app.schedule.scheduler import send_practice_to_user
from data.db import get_users_pending_for_today, get_current_weekday


logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo(DEFAULT_TZ)


async def resend_missed_practices() -> None:
    """Находит пользователей, которым сегодня ещё не отправляли практику,
    и чьё время уведомлений уже наступило, и доотправляет им практику.
    """
    current_time = datetime.now(MOSCOW_TZ).strftime("%H:%M")
    current_weekday = get_current_weekday()

    users = get_users_pending_for_today(current_time)
    if not users:
        print(f"Нет пользователей для доотправки практики на {current_time}")
        return

    print(f"Найдено {len(users)} пользователей для доотправки практики на {current_time}")

    application = Application.builder().token(BOT_TOKEN).build()

    await application.initialize()

    try:
        # Контекст, совместимый с send_practice_to_user: нужен только bot
        context = SimpleNamespace(bot=application.bot)

        for user_id, chat_id in users:
            try:
                await send_practice_to_user(context, user_id, chat_id, current_weekday)
                print(f"Практика доотправлена пользователю {user_id}")
            except Exception as e:
                logger.error(f"Ошибка доотправки практики пользователю {user_id}: {e}")
    finally:
        await application.shutdown()


def main() -> None:
    asyncio.run(resend_missed_practices())


if __name__ == "__main__":
    main()

