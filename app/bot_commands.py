"""Меню команд Telegram (список слева от поля ввода)."""

from telegram import BotCommand


async def setup_bot_commands(application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("favorite", "Избранное 🧡"),
            BotCommand("change_mode", "Изменить режим"),
            BotCommand("donate", "Донаты"),
            BotCommand("progress", "Мой прогресс"),
            BotCommand("suggest", "Порекомендовать практику"),
            BotCommand("help", "Помощь и вопросы"),
            BotCommand("start", "Начать сначала"),

        ]
    )
