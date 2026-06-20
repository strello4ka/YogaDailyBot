"""Меню команд Telegram (список слева от поля ввода)."""

from telegram import BotCommand


async def setup_bot_commands(application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Начать сначала"),
            BotCommand("change_mode", "Изменить режим"),
            BotCommand("suggest", "Порекомендовать практику"),
            BotCommand("donate", "Донаты"),
            BotCommand("progress", "Мой прогресс"),
            BotCommand("help", "Помощь и вопросы"),
        ]
    )
