"""Handler for secret command.
Обработчик команды /secret для массовой рассылки сообщений всем пользователям.
Доступен только администратору бота.
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes

# ID администратора бота (только этот пользователь может использовать /secret)
ADMIN_USER_ID = 946774551

logger = logging.getLogger(__name__)


async def secret_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /secret для массовой рассылки.
    
    Проверяет права доступа и запрашивает сообщение для рассылки.
    Доступна только администратору (user_id = 946774551).
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    user_id = update.effective_user.id
    
    # Проверяем, что команду вызвал администратор
    if user_id != ADMIN_USER_ID:
        logger.warning(f"Попытка использования /secret пользователем {user_id} (не администратор)")
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return
    
    # Устанавливаем состояние ожидания сообщения для рассылки
    context.user_data['waiting_for_secret'] = True
    
    # Запрашиваем сообщение
    request_text = (
        "📢 *Массовая рассылка*\n\n"
        "Отправь текст сообщения или фото с подписью.\n"
        "Сообщение будет отправлено всем пользователям бота.\n\n"
        "💡 *Совет:* Если хочешь отправить только фото без текста, отправь фото с подписью и оставь подпись пустой."
    )
    
    await update.message.reply_text(request_text, parse_mode='Markdown')
    logger.info(f"Администратор {user_id} начал процесс массовой рассылки")


async def handle_secret_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода сообщения для массовой рассылки.
    
    Принимает текст или фото с подписью и отправляет всем пользователям.
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
    """
    user_id = update.effective_user.id
    
    # Проверяем права доступа
    if user_id != ADMIN_USER_ID:
        return
    
    # Проверяем, что пользователь в состоянии ожидания рассылки
    if not context.user_data.get('waiting_for_secret'):
        return
    
    # Убираем состояние ожидания
    context.user_data.pop('waiting_for_secret', None)
    
    # Получаем всех пользователей из базы данных
    from data.db import get_all_users, get_next_broadcast_batch_id, save_broadcast_message
    users = get_all_users()
    
    if not users:
        await update.message.reply_text("❌ В базе данных нет пользователей для рассылки.")
        logger.warning("Попытка рассылки при отсутствии пользователей в БД")
        return
    
    # Определяем тип сообщения (текст или фото)
    has_photo = update.message.photo is not None and len(update.message.photo) > 0
    message_text = update.message.caption if has_photo else update.message.text
    photo_file_id = update.message.photo[-1].file_id if has_photo else None
    message_type = 'photo' if has_photo else 'text'
    
    # Одна партия рассылки — один batch_id для всех сообщений
    broadcast_batch_id = get_next_broadcast_batch_id()
    
    # Подтверждаем начало рассылки
    total_users = len(users)
    await update.message.reply_text(
        f"🚀 Начинаю рассылку для {total_users} пользователей...\n"
        f"Это может занять некоторое время."
    )
    
    logger.info(f"Начало массовой рассылки администратором {user_id}. "
                f"Пользователей: {total_users}, Тип: {'фото с подписью' if has_photo else 'текст'}, batch_id={broadcast_batch_id}")
    
    success_count = 0
    error_count = 0
    errors = []
    
    for idx, user_data in enumerate(users, 1):
        try:
            target_user_id, chat_id = user_data[0], user_data[1]
            
            if has_photo:
                sent_message = await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file_id,
                    caption=message_text if message_text else None,
                    parse_mode='Markdown' if message_text else None
                )
            else:
                sent_message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode='Markdown'
                )
            
            save_broadcast_message(
                broadcast_batch_id=broadcast_batch_id,
                user_id=target_user_id,
                chat_id=chat_id,
                message_id=sent_message.message_id,
                message_type=message_type,
                message_text=message_text,
                photo_file_id=photo_file_id
            )
            success_count += 1
            
            if idx % 10 == 0:
                logger.info(f"Прогресс рассылки: {idx}/{total_users} пользователей обработано")
            
            if idx < total_users:
                await asyncio.sleep(0.05)
                
        except Exception as e:
            error_count += 1
            error_msg = f"Ошибка отправки пользователю {target_user_id} (chat_id: {chat_id}): {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
    
    report = (
        f"✅ *Рассылка завершена*\n\n"
        f"📊 *Статистика:*\n"
        f"• Всего пользователей: {total_users}\n"
        f"• Успешно отправлено: {success_count}\n"
        f"• Ошибок: {error_count}\n\n"
        f"Используй /secret_delete для удаления или /secret_edit для редактирования."
    )
    if errors:
        error_preview = "\n".join(errors[:5])
        if len(errors) > 5:
            error_preview += f"\n... и еще {len(errors) - 5} ошибок"
        report += f"\n\n⚠️ *Ошибки:*\n`{error_preview}`"
    
    await update.message.reply_text(report, parse_mode='Markdown')
    logger.info(f"Массовая рассылка завершена. Успешно: {success_count}, Ошибок: {error_count}")


async def secret_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление последней массовой рассылки: удаляет все сообщения у пользователей и записи в БД."""
    if update.effective_user.id != ADMIN_USER_ID:
        logger.warning(f"Попытка /secret_delete пользователем {update.effective_user.id}")
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return
    
    from data.db import get_latest_broadcast_messages, delete_latest_broadcast
    messages = get_latest_broadcast_messages()
    
    if not messages:
        await update.message.reply_text("❌ Нет сохранённых рассылок для удаления.")
        return
    
    total = len(messages)
    await update.message.reply_text(f"🗑️ Удаляю {total} сообщений рассылки...")
    
    success_count = 0
    error_count = 0
    errors = []
    for target_user_id, chat_id, message_id, *_ in messages:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            success_count += 1
            if success_count % 10 == 0:
                await asyncio.sleep(0.05)
        except Exception as e:
            error_count += 1
            errors.append(f"user {target_user_id}: {str(e)}")
            logger.error(f"Ошибка удаления сообщения {message_id}: {e}")
    
    delete_latest_broadcast()
    
    report = (
        f"✅ *Удаление завершено*\n\n"
        f"• Всего: {total}\n"
        f"• Удалено: {success_count}\n"
        f"• Ошибок: {error_count}"
    )
    if errors:
        report += f"\n\n⚠️ Ошибки: `{' '.join(errors[:3])}`"
    await update.message.reply_text(report, parse_mode='Markdown')
    logger.info(f"Удаление рассылки завершено. Удалено: {success_count}, Ошибок: {error_count}")


async def secret_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос нового текста/подписи для редактирования последней рассылки."""
    if update.effective_user.id != ADMIN_USER_ID:
        logger.warning(f"Попытка /secret_edit пользователем {update.effective_user.id}")
        await update.message.reply_text("❌ У тебя нет доступа к этой команде.")
        return
    
    from data.db import get_latest_broadcast_messages, get_latest_broadcast_meta
    messages = get_latest_broadcast_messages()
    meta = get_latest_broadcast_meta()
    
    if not messages:
        await update.message.reply_text("❌ Нет сохранённых рассылок для редактирования.")
        return
    
    message_type, _, photo_file_id = meta
    context.user_data['waiting_for_secret_edit'] = True
    context.user_data['edit_message_type'] = message_type
    context.user_data['edit_photo_file_id'] = photo_file_id
    
    if message_type == 'photo':
        request_text = (
            "✏️ *Редактирование рассылки*\n\n"
            "Текущая рассылка — фото с подписью.\n"
            "Отправь *новый текст подписи* (без нового фото).\n\n"
            "Разметка Markdown: *жирный*, [ссылка](url)."
        )
    else:
        request_text = (
            "✏️ *Редактирование рассылки*\n\n"
            "Текущая рассылка — текст.\n"
            "Отправь *новый текст сообщения*.\n\n"
            "Разметка Markdown: *жирный*, [ссылка](url)."
        )
    await update.message.reply_text(request_text, parse_mode='Markdown')
    logger.info(f"Администратор {update.effective_user.id} начал редактирование рассылки")


async def handle_secret_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода нового текста для редактирования последней рассылки."""
    if update.effective_user.id != ADMIN_USER_ID:
        return
    if not context.user_data.get('waiting_for_secret_edit'):
        return
    
    context.user_data.pop('waiting_for_secret_edit', None)
    message_type = context.user_data.pop('edit_message_type', None)
    photo_file_id = context.user_data.pop('edit_photo_file_id', None)
    
    from data.db import get_latest_broadcast_messages
    messages = get_latest_broadcast_messages()
    if not messages:
        await update.message.reply_text("❌ Не найдено сообщений для редактирования.")
        return
    
    # Новый контент: только текст (фото не меняем)
    has_photo = update.message.photo is not None and len(update.message.photo) > 0
    new_text = update.message.caption if has_photo else (update.message.text or "")
    
    if has_photo and message_type == 'photo':
        await update.message.reply_text(
            "⚠️ Telegram не позволяет заменить фото в уже отправленных сообщениях.\n"
            "Отправь только текст — будет изменена подпись. Или удали рассылку и создай новую."
        )
        return
    if has_photo and message_type == 'text':
        await update.message.reply_text("⚠️ Нельзя заменить текстовую рассылку на фото. Удали рассылку и создай новую.")
        return
    
    total = len(messages)
    await update.message.reply_text(f"✏️ Редактирую {total} сообщений...")
    
    success_count = 0
    error_count = 0
    errors = []
    for target_user_id, chat_id, message_id, msg_type, *_ in messages:
        try:
            if msg_type == 'photo':
                await context.bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=new_text,
                    parse_mode='Markdown'
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=new_text,
                    parse_mode='Markdown'
                )
            success_count += 1
            if success_count % 10 == 0:
                await asyncio.sleep(0.05)
        except Exception as e:
            error_count += 1
            errors.append(f"user {target_user_id}: {str(e)}")
            logger.error(f"Ошибка редактирования сообщения {message_id}: {e}")
    
    report = (
        f"✅ *Редактирование завершено*\n\n"
        f"• Всего: {total}\n"
        f"• Отредактировано: {success_count}\n"
        f"• Ошибок: {error_count}"
    )
    if errors:
        report += f"\n\n⚠️ Ошибки: `{' '.join(errors[:3])}`"
    await update.message.reply_text(report, parse_mode='Markdown')
    logger.info(f"Редактирование рассылки завершено. Успешно: {success_count}, Ошибок: {error_count}")



