"""/start and onboarding handler for YogaDailyBot.
старт и онбординг.
"""

import asyncio
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext
from data.db import activate_user_by_mood
from data.db import get_current_weekday, get_yoga_practice_by_weekday_order
from app.schedule.scheduler import format_practice_message

from .keyboards import (
    get_by_mood_reply_keyboard,
    get_choose_mode_keyboard,
    get_mode_choice_keyboard,
    get_start_onboarding_keyboard,
    get_welcome_keyboard,
)


def validate_time_format(time_str: str) -> tuple[bool, str]:
    """Проверяет формат времени и возвращает результат валидации.
    
    Args:
        time_str: Строка с временем (например, "09:30", "9:30", "9.30")
    
    Returns:
        tuple: (is_valid, error_message или formatted_time)
    """
    # Убираем пробелы
    time_str = time_str.strip()
    
    # Заменяем точку на двоеточие
    time_str = time_str.replace('.', ':')
    
    # Проверяем формат ЧЧ:ММ или Ч:ММ
    pattern = r'^(\d{1,2}):(\d{2})$'
    match = re.match(pattern, time_str)
    
    if not match:
        return False, "Хм, такой формат времени я не понимаю."
    
    hour = int(match.group(1))
    minute = int(match.group(2))
    
    # Проверяем диапазон часов и минут
    if hour < 0 or hour > 23:
        return False, "Ой, часы должны быть от 0 до 23."
    
    if minute < 0 or minute > 59:
        return False, "Ой, минуты должны быть от 00 до 59."
    
    # Форматируем время в стандартный вид ЧЧ:ММ
    formatted_time = f"{hour:02d}:{minute:02d}"
    return True, formatted_time


async def send_reminder_4h(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет напоминание через 4 часа после выбора времени.
    
    Args:
        context: Контекст бота с данными пользователя
    """
    job = context.job
    chat_id = job.data['chat_id']
    user_id = job.data['user_id']
    
    reminder_text = (
        "Мы уже почти готовы начать долгий и счастливый путь к движению, "
        "осталось выбрать время, когда хочешь получать сообщения"
    )
    
    try:
        await context.bot.send_message(chat_id, reminder_text)
    except Exception as e:
        print(f"Ошибка отправки напоминания 4ч: {e}")


async def send_reminder_24h(context: ContextTypes.DEFAULT_TYPE):
    """Отправляет напоминание через 24 часа после выбора времени.
    
    Args:
        context: Контекст бота с данными пользователя
    """
    job = context.job
    chat_id = job.data['chat_id']
    user_id = job.data['user_id']
    
    reminder_text = (
        "Эй, мы так и не начали\n"
        "Если не выберешь время сегодня, придётся отложить старт..а жаль, тебя ждет отличное занятие!"
    )
    
    try:
        await context.bot.send_message(chat_id, reminder_text)
    except Exception as e:
        print(f"Ошибка отправки напоминания 24ч: {e}")


async def schedule_reminders(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Планирует отправку напоминаний через 4 и 24 часа.
    
    Перед планированием новых напоминаний отменяет существующие для этого пользователя,
    чтобы избежать дублирования напоминаний при повторных вызовах функции.
    
    Args:
        context: Контекст бота
        chat_id: ID чата пользователя
        user_id: ID пользователя
    """
    # Проверяем, что JobQueue доступен
    if not hasattr(context, 'job_queue') or context.job_queue is None:
        print("JobQueue недоступен - напоминания не будут отправлены")
        return
    
    # Сначала отменяем существующие напоминания для этого пользователя,
    # чтобы избежать дублирования при повторных вызовах функции
    await cancel_reminders(context, user_id)
    
    job_data = {'chat_id': chat_id, 'user_id': user_id}
    
    try:
        # Планируем напоминание через 4 часа
        context.job_queue.run_once(
            send_reminder_4h,
            when=timedelta(hours=4),
            data=job_data,
            name=f"reminder_4h_{user_id}"
        )
        
        # Планируем напоминание через 24 часа
        context.job_queue.run_once(
            send_reminder_24h,
            when=timedelta(hours=24),
            data=job_data,
            name=f"reminder_24h_{user_id}"
        )
    except Exception as e:
        print(f"Ошибка планирования напоминаний: {e}")


async def cancel_reminders(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Отменяет запланированные напоминания при выборе времени.
    
    Использует несколько методов для отмены задач, чтобы гарантировать их удаление:
    1. Пытается найти задачи через get_jobs_by_name и вызвать schedule_removal
    2. Если это не работает, пытается удалить через scheduler.remove_job
    
    Args:
        context: Контекст бота
        user_id: ID пользователя
    """
    print(f"=== DEBUG: cancel_reminders вызвана для user_id={user_id} ===")
    
    # Проверяем, что JobQueue доступен
    if not hasattr(context, 'job_queue') or context.job_queue is None:
        print(f"=== DEBUG: JobQueue недоступен для user_id={user_id} - не можем отменить напоминания ===")
        return
    
    job_names = [f"reminder_4h_{user_id}", f"reminder_24h_{user_id}"]
    cancelled_count = 0
    
    try:
        job_queue = context.job_queue
        
        # Метод 1: Пытаемся найти и отменить задачи через get_jobs_by_name
        # Это предпочтительный метод для python-telegram-bot
        for job_name in job_names:
            try:
                # Получаем все задачи с таким именем (их может быть несколько)
                jobs = job_queue.get_jobs_by_name(job_name)
                if jobs:
                    for job in jobs:
                        job.schedule_removal()
                        cancelled_count += 1
                        print(f"=== DEBUG: Задача '{job_name}' помечена на удаление через schedule_removal ===")
                else:
                    print(f"=== DEBUG: Задача '{job_name}' не найдена через get_jobs_by_name ===")
            except Exception as e:
                print(f"=== DEBUG: Ошибка при отмене задачи '{job_name}' через get_jobs_by_name: {e} ===")
        
        # Метод 2: Дополнительно пытаемся удалить через scheduler напрямую
        # Это нужно на случай, если первый метод не сработал
        try:
            scheduler = job_queue.scheduler
            all_jobs = scheduler.get_jobs()
            existing_job_ids = [job.id for job in all_jobs]
            print(f"=== DEBUG: Все задачи в scheduler: {existing_job_ids} ===")
            
            for job_name in job_names:
                try:
                    job = scheduler.get_job(job_name)
                    if job:
                        scheduler.remove_job(job_name)
                        cancelled_count += 1
                        print(f"=== DEBUG: Задача '{job_name}' удалена через scheduler.remove_job ===")
                except Exception as e:
                    # Игнорируем ошибку, если задача уже удалена или не существует
                    print(f"=== DEBUG: Задача '{job_name}' не найдена в scheduler или уже удалена: {e} ===")
        except Exception as e:
            print(f"=== DEBUG: Ошибка при доступе к scheduler: {e} ===")
        
        print(f"=== DEBUG: Всего отменено задач для user_id={user_id}: {cancelled_count} ===")
                
    except Exception as e:
        print(f"=== DEBUG: Критическая ошибка при отмене напоминаний для user_id={user_id}: {e} ===")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик /start: сброс и первый экран онбординга."""
    context.user_data.pop('waiting_for_practice_suggestion', None)
    context.user_data.pop('waiting_for_time', None)
    context.user_data.pop('is_time_change', None)
    context.user_data.pop('by_mood_self_step', None)
    context.user_data.pop('by_mood_self_time', None)

    from data.db import set_user_onboarding_required
    user_id = update.effective_user.id
    set_user_onboarding_required(user_id)

    user = update.effective_user

    intro = (
        f"Привет, *{user.first_name}* 🧡\n\n"
        "Я, твой YogaDailyBot, помогу тебе чаще двигаться и не терять контакт с телом 🔋\n\n"
        "Со мной тебе не нужно будет тратить время на поиск, ведь я храню большой каталог самых приятных практик от разных преподавателей, в том числе от владельца бота @strello4ka. "
        "Каталог постоянно растет и обновляется. А практики подобраны сбалансировано и разнообразно: бодрящая разминка на все тело, изолированная на пресс, "
        "здоровая спина, релакс вытяжение...перечислять можно долго, это все указывается в описании практики. "
        "Ее можно открыть тут в Telegram или перейти по ссылке на Youtube.\n\n"
        "У меня есть несколько режимов работы для выбора под твой запрос и образ жизни.\n\n"
        "Далее ты можешь посмотреть пример практики или сразу перейти к выбору режима 👇"
    )

    msg = update.effective_message
    if not msg:
        return
    await msg.reply_text(
        intro,
        reply_markup=get_start_onboarding_keyboard(),
        parse_mode='Markdown',
    )


async def onboarding_open_mode_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход к выбору режима с экрана /start и после просмотра примера."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    chat_id = update.effective_chat.id
    mode_text = (
        "🌀 *Daily* — для тех, кто хочет мягко внедрить привычку заниматься ежедневно и не перегорать.\n"
        "Выбираешь удобное время, и дальше каждый день бот присылает практику в это время.\n"
        "Неделя содержит сбалансированный набор практик:\n"
        "• 2-3 бодрые, короткие\n"
        "• по вторникам всегда здоровая спина: работа с осанкой, спиной и шеей\n"
        "• по пятницам что-то необычное для развития кругозора и получения нового опыта\n"
        "• в выходные практики чуть длиннее (суббота - горячая активная, воскресенье - релакс растяжка)\n"
        "• плюс бонус: приходит один раз в неделю в дополнение к основной практике. Это может быть дыхательная техника, техники для расслабления тела, отстройка асан, изучение балансов на руках.\n"
        "Ты не заметишь напряга, но тело скажет \"спасибо\" и станет радовать тебя отражением в зеркале!\n\n"
        "🌀 *By mood* — для тех, кто хочет делать зарядки и разминки по состоянию \"здесь и сейчас\", но без траты времени на поиск качественного контента.\n"
        "Нажимаешь кнопку под настроение, и бот сразу подбирает подходящую практику под твой запрос: \"Ленивые дни\", \"Пятиминутка\", \"Практика дня\" и т.д. Также можно самому выбрать время и интенсивность.\n\n"
        "Оба режима помогают практиковать регулярно, просто разным способом:\n"
        "*Daily* — через привычку и стабильность, *By mood* — через гибкость и свободу выбора.\n\n"
        "Выбирай то, что ближе тебе сейчас, изменить режим можно в любой момент в меню 🧡"
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=mode_text,
        reply_markup=get_mode_choice_keyboard(),
        parse_mode='Markdown',
    )


async def onboarding_show_example_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет пример практики без влияния на прогресс и расписание."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    chat_id = update.effective_chat.id

    weekday = get_current_weekday()
    sample = get_yoga_practice_by_weekday_order(weekday, 1)
    if not sample:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Не смогла подобрать пример практики, но ты можешь сразу перейти к выбору режима 👇",
            reply_markup=get_choose_mode_keyboard(),
        )
        return

    (
        _practice_id,
        _title,
        video_url,
        time_practices,
        channel_name,
        _description,
        my_description,
        intensity,
        _practice_weekday,
        _created_at,
        _updated_at,
    ) = sample
    text = format_practice_message(
        day_number=1,
        my_description=my_description,
        time_practices=time_practices,
        intensity=intensity,
        channel_name=channel_name,
        video_url=video_url,
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='Markdown',
        disable_web_page_preview=False,
        reply_markup=get_choose_mode_keyboard(),
    )


async def mode_pick_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь выбрал Daily — показываем описание программы и кнопку «Выбрать время»."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user = update.effective_user
    chat_id = update.effective_chat.id

    from data.db import get_user_bot_mode, set_user_daily_pending

    prev = get_user_bot_mode(user.id)
    if prev == "daily":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Ты уже в режиме *Daily*. Время рассылки можно поменять кнопкой «Изменить время».",
            parse_mode="Markdown",
        )
        return
    if prev == "by_mood":
        set_user_daily_pending(user.id)
    welcome_text_1 = (
        f"Режим *Daily* - мой фаворит!🧡\n\n"
        "Больше никакого скроллинга YouTube - просто открой сообщение и разомнись.\n"
        "Осталось *выбрать время* и можно начинать наш YogaDaily путь!"    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=welcome_text_1,
        reply_markup=get_welcome_keyboard(),
        parse_mode='Markdown',
    )


async def mode_pick_by_mood_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Режим By mood: без рассылки по времени, сразу клавиатура фильтров."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    user = update.effective_user
    chat_id = update.effective_chat.id

    from data.db import get_user_bot_mode

    if get_user_bot_mode(user.id) == "by_mood":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Ты уже в режиме *By mood*. Выбирай фильтр на клавиатуре ниже.",
            parse_mode="Markdown",
            reply_markup=get_by_mood_reply_keyboard(),
        )
        return

    activate_user_by_mood(
        user.id,
        chat_id,
        user_name=user.first_name,
        user_nickname=user.username,
    )
    context.user_data.pop('waiting_for_time', None)
    context.user_data.pop('is_time_change', None)
    text = (
        "Режим *By mood* включён: расписание по времени сейчас выключено.\n\n"
        "Нажимай кнопку — пришлю подходящую практику из базы. "
        "Команда *изменить режим* — в меню команд (косая черта слева от поля ввода).\n\n"
        "Пункт «сам решу» — пошагово: сначала длительность, потом интенсивность."
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='Markdown',
        reply_markup=get_by_mood_reply_keyboard(),
    )


async def want_start_callback(update: Update, context: CallbackContext):
    """Обработчик нажатия кнопки "Выбрать время".
    
    Показывает пользователю инструкцию по вводу времени и сразу запрашивает ввод.
    Планирует напоминания через 4 и 24 часа.
    Это второй шаг в онбординге.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    print("=== want_start_callback вызван ===")
    
    # Получаем callback query (нажатие кнопки)
    query = update.callback_query
    print(f"Callback data: {query.data}")
    
    # Отвечаем на callback, чтобы убрать "часики" у кнопки
    await query.answer()
    
    # Получаем данные пользователя
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Очищаем другие состояния перед установкой нового
    context.user_data.pop('waiting_for_practice_suggestion', None)
    # Важно: явно удаляем флаг is_time_change, чтобы гарантировать онбординг,
    # а не изменение времени (флаг мог остаться от предыдущих действий)
    context.user_data.pop('is_time_change', None)
    
    # Устанавливаем состояние ожидания ввода времени
    context.user_data['waiting_for_time'] = True
    
    # Сообщение о вводе времени
    time_input_text = (
        "Супер!\n\n"
        "Давай выберем время, в которое ты хочешь получать сообщения, рассылка начнется с завтрашнего дня.\n"
        "*Введи время в формате ЧЧ.ММ (например, 09.30)*\n\n"
        "PS. Время учитывается по МСК"
    )
    
    # Отправляем новое сообщение (не редактируем старое)
    await context.bot.send_message(
        chat_id=chat_id,
        text=time_input_text,
        parse_mode='Markdown'
    )
    
    # Планируем напоминания через 4 и 24 часа (если JobQueue доступен)
    if hasattr(context, 'job_queue') and context.job_queue is not None:
        await schedule_reminders(context, chat_id, user_id)
    else:
        print("JobQueue недоступен - напоминания не будут отправлены")


async def handle_time_input(update: Update, context: CallbackContext):
    """Обработчик ввода времени для онбординга (первый ввод времени).
    
    Валидирует введенное время и сохраняет его.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    print(f"=== DEBUG: handle_time_input (онбординг) вызвана ===")
    print(f"User data: {context.user_data}")
    print(f"Waiting for time: {context.user_data.get('waiting_for_time')}")
    print(f"Is time change: {context.user_data.get('is_time_change')}")
    
    # Проверяем, что пользователь в состоянии ожидания ввода времени
    # И что это НЕ изменение времени (для онбординга)
    if not context.user_data.get('waiting_for_time') or context.user_data.get('is_time_change'):
        print("=== DEBUG: Пользователь не в состоянии ожидания времени ИЛИ это изменение времени ===")
        return
    
    # Получаем введенное время
    time_input = update.message.text
    print(f"=== DEBUG: Введенное время: '{time_input}' ===")
    
    # Валидируем формат времени
    is_valid, result = validate_time_format(time_input)
    
    if not is_valid:
        # Показываем ошибку и просим ввести заново
        await update.message.reply_text(
            f"🚨 {result}\n\n"
            "Попробуй еще раз в формате ЧЧ.ММ"
        )
        return
    
    # Время валидно, сохраняем его
    selected_time = result
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Убираем состояние ожидания
    context.user_data.pop('waiting_for_time', None)
    
    # Отменяем запланированные напоминания
    await cancel_reminders(context, user_id)
    
    # Сохраняем время в базу данных
    from data.db import save_user_time
    user_name = update.effective_user.first_name
    user_nickname = update.effective_user.username  # Никнейм пользователя из Telegram
    save_success = save_user_time(user_id, chat_id, selected_time, user_name, user_nickname=user_nickname)
    
    if not save_success:
        print(f"Ошибка сохранения времени пользователя {user_id} в БД")
    
    # TODO: Настроить расписание для отправки
    # await schedule_daily_message(user_id, selected_time)
    
    # Сообщение для онбординга (первый ввод времени)
    success_text = (
        f"Готово ✔️\n\n"
        f"Твое время для практики *{selected_time}*\n"
        "Начиная *с завтрашнего дня*, я буду присылать тебе ссылку на видео в это время автоматически.\n" 
        "*Главное - не отключай мой звук, а то пропустишь!*\n\n"
        "Изменить время можно в любой момент."
    )
    
    # Отправляем сообщение об успешной настройке (без кнопок)
    await update.message.reply_text(
        success_text,
        parse_mode='Markdown',
        disable_web_page_preview=True  # Отключаем превью видео
    )
    
    # Также показываем Reply-клавиатуру для удобства
    from .keyboards import get_main_reply_keyboard
    await update.message.reply_text(
        "Внизу у тебя *появились кнопки* режима Daily:\n\n"
        "🕓 *Изменить время* — жми, чтобы изменить время рассылки\n"
        "💡 *Советы* — жми обязательно\n"
        "⏸ *Пауза* — приостановить или возобновить ежедневную рассылку\n\n"
        "Команды *предложить практику*, *донаты* и *мой прогресс* — в меню команд (список слева от поля ввода).\n\n"
        "Присоединяйся в [коммьюнити бота](https://t.me/+AH0Kv1b97Ak4Y2Zi), чтобы делиться результатами и рассказывать о проблемах\n\n"
        "Встретимся завтра! А пока можешь почитать советы и [выполнить практику из примера](https://youtu.be/oTzetTgYpSU?si=_V8LNx3i3Iq5zeoH) ",
        reply_markup=get_main_reply_keyboard(),
        parse_mode='Markdown',
        disable_web_page_preview=True  # Отключаем предпросмотр видео
    )




async def back_to_hours_callback(update: Update, context: CallbackContext):
    """Обработчик кнопки "Назад к часам" - больше не используется.
    
    Оставлен для совместимости, но не вызывается.
    """
    pass

