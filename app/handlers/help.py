"""Handler for /help command."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for help, existing tips and existing suggestion flow."""
    context.user_data.pop("waiting_for_practice_suggestion", None)
    context.user_data.pop("waiting_for_time", None)

    await update.effective_message.reply_text(
        "Тут ты можешь почитать частые вопросы, советы и порекомендовать свои любимые "
        "видео с YouTube. Если хочешь сообщить об ошибке или предложить идею, то пиши @strello4ka.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Частые вопросы", callback_data="help_faq")],
            [InlineKeyboardButton("Советы", callback_data="help_tips")],
            [InlineKeyboardButton("Порекомендовать практику", callback_data="help_suggest")],
        ]),
    )


async def help_section_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data == "help_faq":
        await update.callback_query.answer()
        await frequent_questions(update, context)
    elif data == "help_tips":
        from app.daily.tips import handle_tips_callback
        await handle_tips_callback(update, context)
    elif data == "help_suggest":
        from app.handlers.suggest_practice import handle_suggest_practice_callback
        await handle_suggest_practice_callback(update, context)


async def frequent_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("waiting_for_practice_suggestion", None)
    context.user_data.pop("waiting_for_time", None)

    help_text = (
        "*Частые вопросы*\n\n"
        "🌀 *1. Что если выполнять утренние практики вечером?*\n"
        "Не воспринимай буквально названия вроде «для бодрого утра» или «перед сном» - это скорее маркетинговые ярлыки на YouTube, чем строгие указания.\n"
        "Но постарайся не выполнять за 1-2 часа до сна практики средней и высокой сложности.\n"
        "Практики низкой сложности можно делать прямо перед сном.\n\n"
        "🌀 *2. Мне нужен VPN?*\n"
        "Если ты находишься в регионе, где доступ к YouTube и Telegram ограничен (например, Россия), для использования бота потребуется VPN.\n\n"
        "🌀 *3. Можно смотреть видео из Telegram без перехода на YouTube?*\n"
        "Если смотришь с телефона, можно запускать видео прямо из Telegram. Никаких лишних переходов, просто нажми ▶️ в сообщении, и практика начнётся.\n\n"
        "🌀 *4. Как порекомендовать свои любимые практики с YouTube для бота?*\n"
        "Нажми кнопку *Порекомендовать практику* в меню. Так ты поможешь мне расширить коллекцию практик в боте!\n\n"
        "Нажми кнопку *Порекомендовать практику* в меню. Так ты поможешь мне расширить коллекцию практик в боте!"
    )

    # Временно скрываем FAQ-кнопку и callback по запросу:
    # - код сохранен в этом файле для быстрого возврата;
    # - текст уже подготовлен с Markdown-разметкой в HELP_SLEEP_QUESTION_MARKDOWN.
    await update.effective_message.reply_text(help_text, parse_mode="Markdown")


HELP_SLEEP_QUESTION_CALLBACK = "help_sleep_question"
HELP_SLEEP_QUESTION_MARKDOWN = (
    "Когда мы делаем что-то активное, у нас повышается пульс, выбрасывается адреналин, "
    "повышается кортизол и т.д., то есть активируется симпатическая нервная система.\n"
    "От этого мы чувствуем прилив сил, повышение концентрации и заряд энергии 🔋\n\n"
    "Перед сном же должна активироваться парасимпатическая нервная система, "
    "что позволяет нам быстро и крепко заснуть 💤\n\n"
    "Когда мы делаем активность перед сном, организму сложнее переключиться "
    "к активации парасимпатической НС.\n"
    "*От этого:*\n"
    "🌀 *дольше засыпаешь*\n"
    "_Плюс появляются эндорфиновые мысли после тренировки из разряда "
    "\"завтра стану лучшей версией себя и выполню сто дел\", которые тоже не дают заснуть._\n"
    "🌀 *пульс во время сна выше, чем обычно* — фоновый стресс\n"
    "🌀 *увеличиваются часы поверхностного сна и снижается глубокий сон* "
    "— вроде спишь 8 часов, а просыпаешься уставшим\n\n"
    "У нас тренировки короткие и не сильно сложные, поэтому ничего критичного нет.\n"
    "Но если это делать систематически, и для вас нагрузка ощутима "
    "(чатуранга заставляет пыхтеть), то лучше не пренебрегать правилом: "
    "*делать минимум за 2 часа до сна*.\n\n"
    "*Но есть практики, которые, наоборот, активируют парасимпатическую НС.* "
    "*Их можно и полезно делать перед сном.*\n"
    "_Маркер для таких практик в боте: сложность — низкая._"
)
