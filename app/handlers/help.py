"""Navigable Rich Message for help, tips and practice suggestions."""

import re

from telegram import Update
from telegram.ext import ContextTypes

from app.onboarding_messages import FILTER_HELP, WEEK_DESCRIPTION
from app.rich_messages import button_row, edit_rich_message, paragraph, send_rich_message


def _title(text):
    return paragraph({"type": "bold", "text": text})


def _back_button():
    return button_row([{"text": "Назад", "callback_data": "help_back"}])


def _simple_html_to_rich_text(value):
    """Reuse onboarding copy while preserving its simple <b> formatting."""
    result = []
    bold = False
    for part in re.split(r"(<b>|</b>)", value):
        if part == "<b>":
            bold = True
        elif part == "</b>":
            bold = False
        elif part:
            result.append({"type": "bold", "text": part} if bold else part)
    return result


def _root_blocks():
    return [
        _title("🫂 Помощь и советы"),
        paragraph(
            "\nТут ты можешь почитать частые вопросы, найти советы и порекомендовать свои любимые видео с YouTube.\n\n"
            "Если хочешь сообщить об ошибке или предложить идею, то пиши @strello4ka."
        ),
        button_row([{"text": "Частые вопросы", "callback_data": "help_faq"}]),
        button_row([{"text": "Советы", "callback_data": "help_tips"}]),
        button_row([{"text": "Порекомендовать практику", "callback_data": "help_suggest"}]),
    ]


def _faq_blocks():
    return [
        _title("Частые вопросы"),
        {"type": "details", "summary": "Что если выполнять утренние практики вечером?", "blocks": [paragraph(
            "Не воспринимай буквально названия вроде «для бодрого утра» или «перед сном» — это скорее маркетинговые ярлыки на YouTube, чем строгие указания.\n\n"
            "Но постарайся не выполнять за 1–2 часа до сна практики средней и высокой сложности. Практики низкой сложности можно делать прямо перед сном."
        )]},
        {"type": "details", "summary": "Мне нужен VPN?", "blocks": [paragraph(
            "Если ты находишься в регионе, где доступ к YouTube и Telegram ограничен (например, Россия), для использования бота потребуется VPN."
        )]},
        {"type": "details", "summary": "Можно смотреть видео из Telegram без перехода на YouTube?", "blocks": [paragraph(
            "Если смотришь с телефона, можно запускать видео прямо из Telegram. Никаких лишних переходов: просто нажми ▶️ в сообщении, и практика начнётся."
        )]},
        {"type": "details", "summary": "Как порекомендовать практику для бота?", "blocks": [paragraph(
            "Нажми кнопку «Порекомендовать практику» в разделе помощи. Так ты поможешь мне расширить коллекцию практик в боте!"
        )]},
        {"type": "details", "summary": "Что означают кнопки-фильтры?", "blocks": [
            paragraph(_simple_html_to_rich_text(FILTER_HELP))
        ]},
        {"type": "details", "summary": "Как составляется неделя?", "blocks": [
            paragraph(_simple_html_to_rich_text(WEEK_DESCRIPTION))
        ]},
        _back_button(),
    ]


def _tips_blocks():
    return [
        _title("Советы"),
        paragraph("\nВот несколько простых рекомендаций, чтобы я смог стать твоим верным другом"),
        {"type": "details", "summary": "Выдели время", "blocks": [paragraph("Бот будет присылать тебе ссылку на видео каждый день. Постарайся выделить 25 минут в течение дня только для себя. Найди подходящее место и отключи уведомления.")]},
        {"type": "details", "summary": "Есть пропущенные дни? Всё в порядке", "blocks": [paragraph("Наши занятия — это не гонка и не короткий марафон. Если не получилось позаниматься вчера, не нужно «нагонять» и выполнять несколько практик подряд. Никакой суеты и насилия над собой. Просто присоединяйся к сегодняшней практике, ведь она пришла именно сегодня не случайно.")]},
        {"type": "details", "summary": "Выбор на мне, но решение за тобой", "blocks": [paragraph("Каждый день ты получаешь новое видео. Если практика не подходит тебе в данный момент, ты всегда можешь заменить её под своё состояние с помощью быстрых кнопок практик.")]},
        {"type": "details", "summary": "Про «утренние» и «вечерние» практики", "blocks": [paragraph("Не воспринимай такие названия буквально. Но постарайся не выполнять за 1–2 часа до сна практики средней и высокой сложности. Практики низкой сложности можно делать прямо перед сном.")]},
        {"type": "details", "summary": "Как строится неделя", "blocks": [
            paragraph(_simple_html_to_rich_text(WEEK_DESCRIPTION))
        ]},
        paragraph("Делай так, как комфортно только тебе.\nПриятных занятий 🧡"),
        _back_button(),
    ]


def _suggest_blocks():
    return [
        paragraph([{"type": "bold", "text": "Хочешь, чтобы твоя любимая практика появилась в YogaDailyBot?"}, "\n🔗 Поделись ссылкой, и я с радостью добавлю её!"]),
        paragraph(["\n", {"type": "bold", "text": "Как предложить?"}, "\nОтправь одним сообщением:\n• ссылку на видео\n• любой комментарий — по желанию"]),
        {
            "type": "blockquote",
            "blocks": [
                paragraph([
                    {"type": "bold", "text": "Пример:"},
                    "\nhttps://youtu.be/oTzetTgYpSU?si=ewHrtkwVb4hFO1NG\n"
                    "моя любимая-любимая практика, бодрит и поднимает настроение 🤤",
                ])
            ],
        },
        _back_button(),
    ]


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for help, existing tips and existing suggestion flow."""
    context.user_data.pop("waiting_for_practice_suggestion", None)
    context.user_data.pop("waiting_for_time", None)

    await send_rich_message(context.bot, update.effective_chat.id, _root_blocks())


async def help_section_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()
    data = query.data
    context.user_data.pop("waiting_for_practice_suggestion", None)
    blocks = {
        "help_back": _root_blocks,
        "help_faq": _faq_blocks,
        "help_tips": _tips_blocks,
        "help_suggest": _suggest_blocks,
    }.get(data)
    if blocks is None:
        return
    await edit_rich_message(context.bot, query.message.chat_id, query.message.message_id, blocks())
    if data == "help_suggest":
        context.user_data["waiting_for_practice_suggestion"] = True


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
