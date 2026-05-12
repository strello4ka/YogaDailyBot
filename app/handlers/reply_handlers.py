"""Reply keyboard handlers for YogaDailyBot.
Обработчики для Reply-клавиатуры с основными функциями бота.
"""

from telegram import Update
from telegram.ext import ContextTypes

from data.db import get_user_bot_mode

_BY_MOOD_LABELS = frozenset(
    {"Практика дня", "Без коврика", "Ленивые дни", "Пятиминутка", "Хард", "Сам решу"}
)


async def handle_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок Reply-клавиатуры.
    
    Обрабатывает текстовые сообщения, соответствующие кнопкам Reply-клавиатуры:
    - "Изменить время" - переадресация к обработчику изменения времени
    - "Предложить практику" - переадресация к обработчику предложения практик
    - "Советы" - переадресация к обработчику советов
    - "Донаты" - переадресация к обработчику донатов
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    message_text = update.message.text
    user_id = update.effective_user.id if update.effective_user else None

    if message_text == "Еще практики":
        from app.mode.extra_practices import send_extra_practices_intro, user_may_use_extra_practices

        if user_id and user_may_use_extra_practices(user_id):
            await send_extra_practices_intro(update, context)
        elif user_id:
            await update.message.reply_text(
                "Кнопка «Еще практики» работает в режимах *Daily* и *Challenge*. "
                "Сейчас у тебя другой режим — переключись через /change_mode, если нужно.",
                parse_mode="Markdown",
            )
        return

    if user_id and get_user_bot_mode(user_id) == "by_mood" and message_text in _BY_MOOD_LABELS:
        await _dispatch_by_mood_button(update, context, message_text)
        return

    if message_text == "Изменить время":
        # Редко: старая reply-клавиатура в Telegram после смены режима.
        mode = get_user_bot_mode(user_id) if user_id else "pending"
        if mode == "by_mood":
            await update.message.reply_text(
                "В режиме *By mood* рассылки по времени нет. "
                "Чтобы снова настроить время — выбери *Daily* через /change_mode.",
                parse_mode="Markdown",
            )
            return
        from .set_time import handle_set_time_callback
        await handle_set_time_callback(update, context)

    elif message_text == "Советы":
        print("=== Обработка кнопки 'Советы' ===")
        from .tips import handle_tips_callback
        await handle_tips_callback(update, context)

    elif message_text == "Пауза":
        from .pause import pause_toggle_command
        await pause_toggle_command(update, context)

    else:
        # Если текст не соответствует ни одной кнопке Reply-клавиатуры,
        # сбрасываем состояние ожидания предложения практики (на случай если оно было установлено)
        # и не обрабатываем (оставляем для других обработчиков)
        context.user_data.pop('waiting_for_practice_suggestion', None)
        return


async def _dispatch_by_mood_button(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if text == "Практика дня":
        from app.by_mood import practice_of_day
        await practice_of_day.handle(update, context)
    elif text == "Без коврика":
        from app.by_mood import no_mat
        await no_mat.handle(update, context)
    elif text == "Ленивые дни":
        from app.by_mood import lazy_days
        await lazy_days.handle(update, context)
    elif text == "Пятиминутка":
        from app.by_mood import five_min
        await five_min.handle(update, context)
    elif text == "Хард":
        from app.by_mood import hard
        await hard.handle(update, context)
    elif text == "Сам решу":
        from app.by_mood.self_decide import start_flow
        await start_flow(update, context)

