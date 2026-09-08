"""Меню команд Telegram (список слева от поля ввода)."""

from telegram import BotCommand


async def setup_bot_commands(application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("donate", "Управление подпиской"),
            BotCommand("schedule", "Расписание"),
            BotCommand("favorite", "Избранное 🧡"),
            BotCommand("progress", "Мой прогресс"),
            BotCommand("practice", "Получить практику"),
            BotCommand("help", "Помощь и советы"),

        ]
    )
