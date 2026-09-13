"""Reply keyboard handlers for YogaDailyBot.
Обработчики для Reply-клавиатуры с основными функциями бота.
"""

from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from app.by_mood.quick_filters import (
    QUICK_FILTERS,
    get_active_quick_filter_by_label,
    get_active_quick_filters,
    record_quick_filter_click,
    select_and_deliver_quick_filter,
)
from data.db import get_user_bot_mode

PRACTICE_KEYBOARD_HINT = "разверни кнопки клавиатуры, чтобы выбрать практику под настроение"
PRACTICE_KEYBOARD_TUTORIAL = (
    Path(__file__).resolve().parent.parent / "assets" / "practice_keyboard_tutorial.mp4"
)
_ALIASES = {spec.label.lower(): spec.label for spec in QUICK_FILTERS.values()}
_BY_MOOD_LABELS = frozenset(_ALIASES) | {"САМ решу"}


async def get_practice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cached_file_id = context.bot_data.get("practice_keyboard_tutorial_file_id")
    configured_video = context.bot_data.get("practice_keyboard_tutorial_video")
    video = cached_file_id or configured_video

    if video:
        message = await update.effective_message.reply_video(
            video=video,
            caption=PRACTICE_KEYBOARD_HINT,
            supports_streaming=True,
        )
    elif PRACTICE_KEYBOARD_TUTORIAL.is_file():
        with PRACTICE_KEYBOARD_TUTORIAL.open("rb") as video_file:
            message = await update.effective_message.reply_video(
                video=video_file,
                caption=PRACTICE_KEYBOARD_HINT,
                supports_streaming=True,
            )
    else:
        await update.effective_message.reply_text(PRACTICE_KEYBOARD_HINT)
        return

    if message.video:
        context.bot_data["practice_keyboard_tutorial_file_id"] = message.video.file_id


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
    from app.onboarding_flow import handle_reply as handle_onboarding_reply
    if await handle_onboarding_reply(update, context):
        return

    message_text = update.message.text
    user_id = update.effective_user.id if update.effective_user else None

    # Любая постоянная reply-кнопка означает, что пользователь ушёл из
    # незавершённого ввода времени в разделе расписания.
    from app.handlers.schedule import cancel_schedule_menu_time
    cancel_schedule_menu_time(context)

    if message_text == "Еще практики":
        from app.daily.extra_practices import send_extra_practices_intro, user_may_use_extra_practices

        if user_id and user_may_use_extra_practices(user_id):
            await send_extra_practices_intro(update, context)
        elif user_id:
            await update.message.reply_text(
                "Кнопка «Еще практики» работает в режимах *Daily* и *Challenge*. "
                "Сейчас у тебя другой режим — переключись через /change_mode, если нужно.",
                parse_mode="Markdown",
            )
        return

    if message_text == "расписание":
        from app.handlers.schedule import schedule_command
        await schedule_command(update, context)
        return

    if user_id and get_user_bot_mode(user_id) in ("by_mood", "daily", "challenge") and message_text in _BY_MOOD_LABELS:
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
        from app.daily.set_time import handle_set_time_callback
        await handle_set_time_callback(update, context)

    elif message_text == "Советы":
        print("=== Обработка кнопки 'Советы' ===")
        from app.daily.tips import handle_tips_callback
        await handle_tips_callback(update, context)

    elif message_text == "Пауза":
        from app.daily.pause import pause_toggle_command
        await pause_toggle_command(update, context)

    else:
        # Если текст не соответствует ни одной кнопке Reply-клавиатуры,
        # сбрасываем состояние ожидания предложения практики (на случай если оно было установлено)
        # и не обрабатываем (оставляем для других обработчиков)
        context.user_data.pop('waiting_for_practice_suggestion', None)
        return


async def _dispatch_by_mood_button(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    canonical = _ALIASES.get(text.lower(), text)
    spec = get_active_quick_filter_by_label(canonical)
    if spec is None:
        spec = next((item for item in QUICK_FILTERS.values() if item.label == canonical), None)
    user = update.effective_user
    chat = update.effective_chat
    if not spec or not user or not chat:
        return

    if spec.pool == "flow":
        record_quick_filter_click(user.id, spec, "by_mood", None)
        from app.by_mood.self_decide import start_flow

        await start_flow(update, context)
        return

    result = await select_and_deliver_quick_filter(
        context,
        user.id,
        chat.id,
        spec,
        "by_mood",
    )
    if result == "empty":
        await update.message.reply_text(spec.empty_message)
    elif result == "failed":
        await update.message.reply_text("Не удалось отправить практику. Попробуй ещё раз.")
