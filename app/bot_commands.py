"""Меню команд Telegram (список слева от поля ввода)."""

from telegram import BotCommand


async def setup_bot_commands(application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Начать сначала (сброс прогресса)"),
            BotCommand("change_mode", "Изменить режим Daily / By mood"),
            BotCommand("suggest", "Предложить практику"),
            BotCommand("donate", "Донаты"),
            BotCommand("progress", "Мой прогресс"),
            BotCommand("tips", "Советы"),
            BotCommand("help", "Помощь"),
        ]
    )
