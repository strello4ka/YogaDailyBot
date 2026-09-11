"""Меню команд Telegram (список слева от поля ввода)."""

from telegram import BotCommand, BotCommandScopeAllPrivateChats


async def setup_bot_commands(application) -> None:
    commands = [
        BotCommand("donate", "💰 Подписка"),
        BotCommand("schedule", "🕐 Расписание"),
        BotCommand("favorite", "🧡 Избранное"),
        BotCommand("progress", "🔋 Мой прогресс"),
        BotCommand("practice", "🧘‍♀️ Получить практику"),
        BotCommand("help", "🫂 Помощь и советы"),
    ]
    await application.bot.set_my_commands(commands)
    await application.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
