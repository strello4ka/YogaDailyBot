import psycopg2
import psycopg2.extras
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo  # Нужен для вычисления дня недели с учётом таймзоны
from typing import Optional  # Для типов, совместимых с Python 3.9
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_db_config, DEFAULT_TZ  # Берём таймзону из конфигурации проекта

logger = logging.getLogger(__name__)

# Приводим my_description к реальным переносам строк, чтобы маркеры из CSV/ручного ввода
# (/n — новая строка, //n — новый абзац) отображались корректно при сохранении и выдаче.
def _decode_my_description(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    decoded = text.replace('//n', '\n\n')
    decoded = decoded.replace('/n', '\n')
    return decoded


def _decode_practice_row(row: Optional[tuple]) -> Optional[tuple]:
    """Декодируем поле my_description в строке из yoga_practices."""
    if not row:
        return row
    row_list = list(row)
    # my_description всегда в позиции 6 во всех выборках yoga_practices, где оно есть
    if len(row_list) > 6:
        row_list[6] = _decode_my_description(row_list[6])
    return tuple(row_list)


def _decode_bonus_practice_row(row: Optional[tuple]) -> Optional[tuple]:
    """Декодируем поле my_description в строке из bonus_practices (позиция 7)."""
    if not row:
        return row
    row_list = list(row)
    if len(row_list) > 7:
        row_list[7] = _decode_my_description(row_list[7])
    return tuple(row_list)

def get_connection():
    """Создает подключение к PostgreSQL базе данных.
    
    Returns:
        psycopg2.connection: Объект подключения к базе данных
    """
    config = get_db_config()
    return psycopg2.connect(**config)

def init_database():
    """Инициализирует базу данных и создает необходимые таблицы.
    
    Создает таблицы:
    - users: для хранения данных пользователей
    - yoga_practices: для хранения йога практик с YouTube
    - practice_logs: для логирования отправленных практик
    
    Поля таблицы yoga_practices:
    - practices_id: уникальный ID практики (SERIAL)
    - title: название видео
    - video_url: ссылка на видео (UNIQUE)
    - time_practices: длительность видео в минутах
    - channel_name: название канала
    - description: описание видео (автоматически с YouTube)
    - my_description: мое описание (заполняется вручную)
    - intensity: интенсивность практики (легкая, средняя, высокая)
    - weekday: день недели (1=понедельник, 7=воскресенье, NULL=любой день)
    - created_at: дата добавления записи
    - updated_at: дата последнего обновления
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Создаем таблицу пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                notify_time VARCHAR(5) NOT NULL,
                user_name TEXT,
                user_phone TEXT,
                user_days INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создаем таблицу йога практик
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yoga_practices (
                practices_id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                video_url TEXT NOT NULL UNIQUE,
                time_practices INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                description TEXT,
                my_description TEXT,
                intensity TEXT,
                weekday INTEGER CHECK (weekday >= 1 AND weekday <= 7),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создаем таблицу бонусных практик, привязанных к основной
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bonus_practices (
                bonus_id SERIAL PRIMARY KEY,
                parent_practice_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                video_url TEXT NOT NULL UNIQUE,
                time_practices INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                description TEXT,
                my_description TEXT,
                intensity TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_practice_id) REFERENCES yoga_practices (practices_id) ON DELETE CASCADE
            )
        ''')
        
        # Создаем таблицу для логирования отправленных практик
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS practice_logs (
                log_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                practice_id INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                day_number INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                FOREIGN KEY (practice_id) REFERENCES yoga_practices (practices_id) ON DELETE CASCADE
            )
        ''')
        
        # Создаем таблицу для предложений пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_suggestions (
                suggestion_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                video_url TEXT NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        ''')
        
        # Создаем таблицу для хранения отправленных сообщений массовой рассылки
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broadcast_messages (
                id SERIAL PRIMARY KEY,
                broadcast_batch_id INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                message_id INTEGER NOT NULL,
                message_type TEXT NOT NULL,
                message_text TEXT,
                photo_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        ''')
        
        # Миграция: удаляем старые поля recommend и comment из таблицы users
        try:
            # Проверяем, существуют ли колонки, и удаляем их
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name IN ('recommend', 'comment')
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]
            
            if 'recommend' in existing_columns:
                cursor.execute('ALTER TABLE users DROP COLUMN recommend')
                print("✅ Колонка recommend удалена из таблицы users")
            
            if 'comment' in existing_columns:
                cursor.execute('ALTER TABLE users DROP COLUMN comment')
                print("✅ Колонка comment удалена из таблицы users")
                
        except Exception as e:
            print(f"⚠️ Ошибка удаления колонок из users: {e}")
        
        # Миграция: добавление столбца is_blocked для пометки заблокировавших бота пользователей
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'is_blocked'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT FALSE")
                print("   ✅ Добавлен столбец is_blocked в таблицу users")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении столбца is_blocked: {e}")

        # Миграция: флаг незавершенного онбординга
        try:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'onboarding_required'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN onboarding_required BOOLEAN DEFAULT FALSE")
                print("   ✅ Добавлен столбец onboarding_required в таблицу users")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении столбца onboarding_required: {e}")
        
        # Создаем индексы для быстрого поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_url ON yoga_practices(video_url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_channel_name ON yoga_practices(channel_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_duration ON yoga_practices(time_practices)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_weekday ON yoga_practices(weekday)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_intensity ON yoga_practices(intensity)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bonus_parent_practice ON bonus_practices(parent_practice_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_bonus_video_url ON bonus_practices(video_url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_practice_logs_user ON practice_logs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_practice_logs_practice ON practice_logs(practice_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_suggestions_user ON user_suggestions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_suggestions_created ON user_suggestions(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_broadcast_messages_batch ON broadcast_messages(broadcast_batch_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_broadcast_messages_created ON broadcast_messages(created_at DESC)')
        
        # Миграция: добавление столбца user_nickname (если еще нет)
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name = 'user_nickname'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE users ADD COLUMN user_nickname TEXT')
                print("   ✅ Добавлен столбец user_nickname в таблицу users")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении столбца user_nickname: {e}")
        
        # Миграция: добавление столбца user_nickname в таблицу user_suggestions (если еще нет)
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'user_suggestions' 
                AND column_name = 'user_nickname'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE user_suggestions ADD COLUMN user_nickname TEXT')
                print("   ✅ Добавлен столбец user_nickname в таблицу user_suggestions")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении столбца user_nickname в user_suggestions: {e}")
        
        try:
            # Обновляем ограничение для yoga_practices до 500 символов
            # Сначала удаляем старое ограничение (если есть)
            cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'yoga_practices' 
                AND constraint_name = 'description_max_length'
            """)
            if cursor.fetchone():
                cursor.execute('ALTER TABLE yoga_practices DROP CONSTRAINT IF EXISTS description_max_length')
                print("   🔄 Удалено старое ограничение для yoga_practices.description")
            
            # Создаем новое ограничение на 500 символов
            cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'yoga_practices' 
                AND constraint_name = 'description_max_length'
            """)
            if not cursor.fetchone():
                cursor.execute('''
                    ALTER TABLE yoga_practices 
                    ADD CONSTRAINT description_max_length 
                    CHECK (description IS NULL OR LENGTH(description) <= 500)
                ''')
                print("   ✅ Добавлено ограничение для yoga_practices.description (500 символов)")
            
            # Обновляем ограничение для bonus_practices до 500 символов
            # Сначала удаляем старое ограничение (если есть)
            cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'bonus_practices' 
                AND constraint_name = 'bonus_description_max_length'
            """)
            if cursor.fetchone():
                cursor.execute('ALTER TABLE bonus_practices DROP CONSTRAINT IF EXISTS bonus_description_max_length')
                print("   🔄 Удалено старое ограничение для bonus_practices.description")
            
            # Создаем новое ограничение на 500 символов
            cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'bonus_practices' 
                AND constraint_name = 'bonus_description_max_length'
            """)
            if not cursor.fetchone():
                cursor.execute('''
                    ALTER TABLE bonus_practices 
                    ADD CONSTRAINT bonus_description_max_length 
                    CHECK (description IS NULL OR LENGTH(description) <= 500)
                ''')
                print("   ✅ Добавлено ограничение для bonus_practices.description (500 символов)")
                
        except Exception as e:
            print(f"⚠️ Ошибка при применении миграции description: {e}")
        
        # Миграция: добавление столбца challenge_start_id для режима челленджа
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'challenge_start_id'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE users ADD COLUMN challenge_start_id INTEGER')
                print("   ✅ Добавлен столбец challenge_start_id в таблицу users")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении столбца challenge_start_id: {e}")

        # Миграция: program_position и last_practice_message_id для трекера прогресса
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'program_position'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE users ADD COLUMN program_position INTEGER DEFAULT 0')
                cursor.execute('UPDATE users SET program_position = user_days WHERE program_position = 0 OR program_position IS NULL')
                print("   ✅ Добавлен столбец program_position в таблицу users")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении столбца program_position: {e}")
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'last_practice_message_id'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE users ADD COLUMN last_practice_message_id BIGINT')
                print("   ✅ Добавлен столбец last_practice_message_id в таблицу users")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении столбца last_practice_message_id: {e}")

        # Миграция: completed_at в practice_logs для отметки «✔️Я сделал!»
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'practice_logs' AND column_name = 'completed_at'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE practice_logs ADD COLUMN completed_at TIMESTAMP')
                print("   ✅ Добавлен столбец completed_at в таблицу practice_logs")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении столбца completed_at: {e}")

        conn.commit()
        conn.close()
        print("PostgreSQL база данных инициализирована успешно")
        
    except Exception as e:
        print(f"Ошибка инициализации PostgreSQL базы данных: {e}")
        conn = None

def save_user_time(user_id: int, chat_id: int, notify_time: str, user_name: str = None, user_phone: str = None, user_nickname: str = None, reset_days: bool = True) -> bool:
    """Сохраняет или обновляет время уведомлений пользователя.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        notify_time: время в формате HH:MM
        user_name: имя пользователя (опционально)
        user_phone: телефон пользователя (опционально)
        user_nickname: никнейм пользователя из Telegram (опционально)
        reset_days: если True, обнуляет счетчик дней (для первого запуска); если False, сохраняет текущий счетчик (для изменения времени)
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if reset_days:
            # Первый запуск (/start) - обнуляем счетчик дней
            cursor.execute('''
                INSERT INTO users (user_id, chat_id, notify_time, user_name, user_phone, user_nickname, user_days)
                VALUES (%s, %s, %s, %s, %s, %s, 0)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    chat_id = EXCLUDED.chat_id,
                    notify_time = EXCLUDED.notify_time,
                    user_name = EXCLUDED.user_name,
                    user_phone = EXCLUDED.user_phone,
                    user_nickname = EXCLUDED.user_nickname,
                    user_days = 0,
                    onboarding_required = FALSE,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, chat_id, notify_time, user_name, user_phone, user_nickname))
        else:
            # Изменение времени - НЕ обнуляем счетчик дней
            cursor.execute('''
                INSERT INTO users (user_id, chat_id, notify_time, user_name, user_phone, user_nickname, user_days)
                VALUES (%s, %s, %s, %s, %s, %s, 0)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    chat_id = EXCLUDED.chat_id,
                    notify_time = EXCLUDED.notify_time,
                    user_name = EXCLUDED.user_name,
                    user_phone = EXCLUDED.user_phone,
                    user_nickname = EXCLUDED.user_nickname,
                    onboarding_required = FALSE,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, chat_id, notify_time, user_name, user_phone, user_nickname))
        
        conn.commit()
        conn.close()
        
        if reset_days:
            print(f"Время пользователя {user_id} сохранено: {notify_time} (счетчик дней обнулен)")
        else:
            print(f"Время пользователя {user_id} изменено на: {notify_time} (счетчик дней сохранен)")
        
        return True
        
    except Exception as e:
        print(f"Ошибка сохранения времени пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def save_user_practice_suggestion(user_id: int, video_url: str, comment: str = None, user_nickname: str = None) -> bool:
    """Сохраняет предложение практики от пользователя в отдельную таблицу.
    
    Args:
        user_id: ID пользователя, предложившего практику
        video_url: ссылка на рекомендуемое видео
        comment: комментарий пользователя к рекомендации (опционально)
        user_nickname: никнейм пользователя из Telegram (опционально)
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Проверяем, что пользователь существует
        cursor.execute('SELECT user_id FROM users WHERE user_id = %s', (user_id,))
        if not cursor.fetchone():
            print(f"Пользователь {user_id} не найден")
            return False
        
        # Добавляем новое предложение в таблицу user_suggestions
        # Сохраняем user_nickname для удобства просмотра предложений
        cursor.execute('''
            INSERT INTO user_suggestions (user_id, video_url, comment, user_nickname)
            VALUES (%s, %s, %s, %s)
        ''', (user_id, video_url, comment, user_nickname))
        
        conn.commit()
        conn.close()
        print(f"Предложение практики от пользователя {user_id} сохранено: {video_url}")
        return True
        
    except Exception as e:
        print(f"Ошибка сохранения предложения практики от пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_user_suggestions(user_id: int, limit: int = 10) -> list:
    """Получает предложения пользователя.
    
    Args:
        user_id: ID пользователя
        limit: максимальное количество предложений (по умолчанию 10)
        
    Returns:
        list: Список кортежей (suggestion_id, video_url, comment, user_nickname, created_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT suggestion_id, video_url, comment, user_nickname, created_at
            FROM user_suggestions 
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        ''', (user_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения предложений пользователя {user_id}: {e}")
        if conn:
            conn.close()
        return []

def get_all_user_suggestions(limit: int = 100) -> list:
    """Получает все предложения пользователей.
    
    Args:
        limit: максимальное количество предложений (по умолчанию 100)
        
    Returns:
        list: Список кортежей (suggestion_id, user_id, video_url, comment, user_nickname, created_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT suggestion_id, user_id, video_url, comment, user_nickname, created_at
            FROM user_suggestions 
            ORDER BY created_at DESC
            LIMIT %s
        ''', (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения всех предложений: {e}")
        if conn:
            conn.close()
        return []

def increment_user_days(user_id: int) -> bool:
    """Увеличивает счетчик дней пользователя на 1.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET user_days = user_days + 1, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (user_id,))
        
        if cursor.rowcount == 0:
            print(f"Пользователь {user_id} не найден")
            return False
        
        conn.commit()
        conn.close()
        print(f"Дни пользователя {user_id} увеличены")
        return True
        
    except Exception as e:
        print(f"Ошибка увеличения дней пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_user_days(user_id: int) -> int:
    """Получает количество дней пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        int: Количество дней или 0 если пользователь не найден
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_days
            FROM users 
            WHERE user_id = %s
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        else:
            return 0
            
    except Exception as e:
        print(f"Ошибка получения дней пользователя {user_id}: {e}")
        if conn:
            conn.close()
        return 0

def reset_user_days(user_id: int) -> bool:
    """Сбрасывает счетчик дней пользователя к 0.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET user_days = 0, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (user_id,))
        
        if cursor.rowcount == 0:
            print(f"Пользователь {user_id} не найден")
            return False
        
        conn.commit()
        conn.close()
        print(f"Счетчик дней пользователя {user_id} сброшен к 0")
        return True
        
    except Exception as e:
        print(f"Ошибка сброса дней пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def get_program_position(user_id: int) -> int:
    """Возвращает позицию в программе (для выбора следующей практики). Не сбрасывается при сбросе прогресса."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(program_position, 0) FROM users WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row is not None else 0
    except Exception as e:
        print(f"Ошибка get_program_position для {user_id}: {e}")
        if conn:
            conn.close()
        return 0


def increment_program_position(user_id: int) -> bool:
    """Увеличивает позицию в программе на 1. Вызывается при каждой отправке практики."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET program_position = COALESCE(program_position, 0) + 1, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (user_id,))
        ok = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return ok
    except Exception as e:
        print(f"Ошибка increment_program_position для {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def set_last_practice_message_id(user_id: int, message_id: int) -> bool:
    """Сохраняет message_id последнего сообщения с практикой (для снятия кнопки при следующей отправке)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET last_practice_message_id = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s
        ''', (message_id, user_id))
        ok = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return ok
    except Exception as e:
        print(f"Ошибка set_last_practice_message_id для {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def get_last_practice_message_id(user_id: int):
    """Возвращает message_id последнего сообщения с практикой или None."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT last_practice_message_id FROM users WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] is not None else None
    except Exception as e:
        print(f"Ошибка get_last_practice_message_id для {user_id}: {e}")
        if conn:
            conn.close()
        return None


def delete_user(user_id: int) -> bool:
    """Удаляет пользователя из базы данных.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
        
        conn.commit()
        conn.close()
        print(f"Пользователь {user_id} удален из базы данных")
        return True
        
    except Exception as e:
        print(f"Ошибка удаления пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_all_users() -> list:
    """Получает список всех пользователей с их данными.
    
    Returns:
        list: Список кортежей (user_id, chat_id, notify_time, user_name, user_phone, user_nickname, user_days)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, chat_id, notify_time, user_name, user_phone, user_nickname, user_days
            FROM users 
            ORDER BY user_id
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения списка пользователей: {e}")
        if conn:
            conn.close()
        return []

def get_users_by_time(notify_time: str) -> list:
    """Получает список пользователей, которые должны получать уведомления в указанное время.
    
    Args:
        notify_time: время в формате HH:MM
        
    Returns:
        list: Список кортежей (user_id, chat_id)
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, chat_id 
            FROM users 
            WHERE notify_time = %s
              AND COALESCE(is_blocked, FALSE) = FALSE
              AND COALESCE(onboarding_required, FALSE) = FALSE
        ''', (notify_time,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения пользователей по времени {notify_time}: {e}")
        if conn:
            conn.close()
        return []


def get_users_pending_for_today(current_time: str) -> list:
    """Возвращает пользователей, которым ещё не отправляли практику сегодня,
    и чьё время уведомлений уже наступило (notify_time <= current_time).

    Используется для повторных попыток: если в слоте не удалось отправить практику,
    пользователь останется без записи в practice_logs за сегодня и будет выбран
    при следующем тике до конца дня.

    Args:
        current_time: текущее время в формате HH:MM (в базовой таймзоне бота)

    Returns:
        list: Список кортежей (user_id, chat_id)
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT u.user_id, u.chat_id
            FROM users u
            WHERE u.notify_time <= %s
              AND COALESCE(u.is_blocked, FALSE) = FALSE
              AND COALESCE(u.onboarding_required, FALSE) = FALSE
              AND NOT EXISTS (
                  SELECT 1
                  FROM practice_logs pl
                  WHERE pl.user_id = u.user_id
                    AND pl.sent_at::date = CURRENT_DATE
              )
            ''',
            (current_time,),
        )

        results = cursor.fetchall()
        conn.close()

        return results

    except Exception as e:
        print(f"Ошибка получения пользователей для сегодняшней отправки на {current_time}: {e}")
        if conn:
            conn.close()
        return []


def get_user_challenge_start_id(user_id: int):
    """Возвращает challenge_start_id пользователя (режим челленджа) или None.
    
    Returns:
        int или None: ID стартовой практики челленджа или None при обычном режиме
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT challenge_start_id FROM users WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] is not None else None
    except Exception as e:
        print(f"Ошибка получения challenge_start_id для {user_id}: {e}")
        if conn:
            conn.close()
        return None


def set_user_challenge(user_id: int, challenge_start_id: int) -> bool:
    """Включает режим челленджа: задаёт стартовый id, обнуляет счётчик дней и позицию в программе.
    program_position обнуляется, чтобы первая отправка в челлендже была «день 1» (практика с challenge_start_id).
    
    Returns:
        bool: True при успехе
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET challenge_start_id = %s, user_days = 0, program_position = 0, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (challenge_start_id, user_id))
        if cursor.rowcount == 0:
            conn.close()
            return False
        conn.commit()
        conn.close()
        print(f"Пользователь {user_id}: режим челленджа с id={challenge_start_id}, дни обнулены")
        return True
    except Exception as e:
        print(f"Ошибка set_user_challenge {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def clear_user_challenge(user_id: int) -> bool:
    """Выключает режим челленджа (challenge_start_id = NULL).
    
    Returns:
        bool: True при успехе
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET challenge_start_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (user_id,))
        conn.commit()
        conn.close()
        print(f"Пользователь {user_id}: режим челленджа выключен")
        return True
    except Exception as e:
        print(f"Ошибка clear_user_challenge {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def set_user_blocked(user_id: int, is_blocked: bool) -> bool:
    """Помечает пользователя как заблокировавшего бота (is_blocked = TRUE) или снимает флаг."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            '''
            UPDATE users
            SET is_blocked = %s, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
            ''',
            (is_blocked, user_id),
        )
        conn.commit()
        conn.close()
        print(f"Пользователь {user_id}: is_blocked={is_blocked}")
        return True
    except Exception as e:
        print(f"Ошибка set_user_blocked {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def get_user_notify_time(user_id: int):
    """Возвращает время уведомления пользователя (HH:MM) или None."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT notify_time, COALESCE(onboarding_required, FALSE) FROM users WHERE user_id = %s',
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        if row[1]:
            return None
        return row[0]
    except Exception as e:
        print(f"Ошибка get_user_notify_time {user_id}: {e}")
        if conn:
            conn.close()
        return None


def is_user_onboarding_required(user_id: int) -> bool:
    """Возвращает True, если пользователь должен завершить/повторить онбординг (после /start)."""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT COALESCE(onboarding_required, FALSE) FROM users WHERE user_id = %s',
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return bool(row[0]) if row else False
    except Exception as e:
        print(f"Ошибка is_user_onboarding_required для {user_id}: {e}")
        if conn:
            conn.close()
        return False


def set_user_onboarding_required(user_id: int) -> bool:
    """Помечает пользователя как требующего повторного онбординга после /start.

    Сбрасывает зависящие от старого состояния поля: challenge_start_id, user_days, program_position,
    а также обнуляет отметки выполненных практик (completed_at) для полного "старта с нуля".
    Если пользователя нет в БД, возвращает True (он пройдёт стандартный онбординг как новый).
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET onboarding_required = TRUE,
                challenge_start_id = NULL,
                user_days = 0,
                program_position = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (user_id,))
        cursor.execute(
            'UPDATE practice_logs SET completed_at = NULL WHERE user_id = %s',
            (user_id,)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка set_user_onboarding_required для {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


# Функции для работы с йога практиками

def add_yoga_practice(title: str, video_url: str, time_practices: int, channel_name: str, description: str = None, my_description: str = None, intensity: str = None, weekday: int = None) -> tuple:
    """Добавляет новую йога практику в базу данных.
    
    Args:
        title: название видео
        video_url: ссылка на видео
        time_practices: длительность видео в минутах
        channel_name: название канала
        description: описание видео (опционально)
        my_description: мое описание (заполняется вручную, опционально)
        intensity: интенсивность практики (опционально)
        weekday: день недели (1=понедельник, 7=воскресенье, None=любой день)
        
    Returns:
        tuple: (success: bool, message: str) - успех операции и сообщение о результате
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Декодируем переносы строк до сохранения, чтобы в базе лежал уже готовый текст
        my_description = _decode_my_description(my_description)
        
        # Обрезаем description до 500 символов (ограничение БД)
        if description and len(description) > 500:
            description = description[:500]
        
        cursor.execute('''
            INSERT INTO yoga_practices (title, video_url, time_practices, channel_name, description, my_description, intensity, weekday)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (title, video_url, time_practices, channel_name, description, my_description, intensity, weekday))
        
        conn.commit()
        conn.close()
        return (True, f"Йога практика добавлена: {title}")
        
    except psycopg2.IntegrityError:
        error_msg = f"Видео с URL {video_url} уже существует в базе данных"
        if conn:
            conn.rollback()
            conn.close()
        return (False, error_msg)
    except Exception as e:
        error_msg = f"Ошибка добавления йога практики: {e}"
        if conn:
            conn.rollback()
            conn.close()
        return (False, error_msg)

def get_yoga_practice_by_id(practice_id: int) -> tuple:
    """Получает йога практику по ID.
    
    Args:
        practice_id: ID практики
        
    Returns:
        tuple: (practices_id, title, video_url, time_practices, channel_name, description, my_description, intensity, weekday, created_at, updated_at) 
               или None если практика не найдена
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, my_description, intensity, weekday, created_at, updated_at
            FROM yoga_practices 
            WHERE practices_id = %s
        ''', (practice_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return _decode_practice_row(result)
        
    except Exception as e:
        print(f"Ошибка получения йога практики {practice_id}: {e}")
        if conn:
            conn.close()
        return None

def get_yoga_practice_by_url(video_url: str) -> tuple:
    """Получает йога практику по URL видео.
    
    Args:
        video_url: ссылка на видео
        
    Returns:
        tuple: (id, title, video_url, time_practices, channel_name, description, my_description, intensity, weekday, created_at, updated_at) 
               или None если практика не найдена
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, my_description, intensity, weekday, created_at, updated_at
            FROM yoga_practices 
            WHERE video_url = %s
        ''', (video_url,))
        
        result = cursor.fetchone()
        conn.close()
        
        return _decode_practice_row(result)
        
    except Exception as e:
        print(f"Ошибка получения йога практики по URL {video_url}: {e}")
        if conn:
            conn.close()
        return None

def get_all_yoga_practices() -> list:
    """Получает список всех йога практик.
    
    Returns:
        list: Список кортежей (practices_id, title, video_url, time_practices, channel_name, description, my_description, weekday, created_at, updated_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, my_description, weekday, created_at, updated_at
            FROM yoga_practices 
            ORDER BY created_at DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return [_decode_practice_row(row) for row in results]
        
    except Exception as e:
        print(f"Ошибка получения списка йога практик: {e}")
        if conn:
            conn.close()
        return []

def get_yoga_practices_by_channel(channel_name: str) -> list:
    """Получает список йога практик по названию канала.
    
    Args:
        channel_name: название канала
        
    Returns:
        list: Список кортежей (practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
            FROM yoga_practices 
            WHERE channel_name = %s
            ORDER BY created_at DESC
        ''', (channel_name,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения йога практик канала {channel_name}: {e}")
        if conn:
            conn.close()
        return []

def get_yoga_practices_by_duration(min_duration: int = None, max_duration: int = None) -> list:
    """Получает список йога практик по длительности.
    
    Args:
        min_duration: минимальная длительность в минутах (опционально)
        max_duration: максимальная длительность в минутах (опционально)
        
    Returns:
        list: Список кортежей (practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if min_duration is not None and max_duration is not None:
            cursor.execute('''
                SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
                FROM yoga_practices 
                WHERE time_practices BETWEEN %s AND %s
                ORDER BY time_practices
            ''', (min_duration, max_duration))
        elif min_duration is not None:
            cursor.execute('''
                SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
                FROM yoga_practices 
                WHERE time_practices >= %s
                ORDER BY time_practices
            ''', (min_duration,))
        elif max_duration is not None:
            cursor.execute('''
                SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
                FROM yoga_practices 
                WHERE time_practices <= %s
                ORDER BY time_practices
            ''', (max_duration,))
        else:
            cursor.execute('''
                SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
                FROM yoga_practices 
                ORDER BY time_practices
            ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения йога практик по длительности: {e}")
        if conn:
            conn.close()
        return []

def get_yoga_practices_by_weekday(weekday: int) -> list:
    """Получает список йога практик для определенного дня недели.
    
    Args:
        weekday: день недели (1=понедельник, 7=воскресенье)
        
    Returns:
        list: Список кортежей (practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
            FROM yoga_practices 
            WHERE weekday = %s OR weekday IS NULL
            ORDER BY RANDOM()
        ''', (weekday,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения йога практик для дня недели {weekday}: {e}")
        if conn:
            conn.close()
        return []

def get_random_yoga_practice_by_weekday(weekday: int) -> tuple:
    """Получает случайную йога практику для определенного дня недели.
    
    Args:
        weekday: день недели (1=понедельник, 7=воскресенье)
        
    Returns:
        tuple: (practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at) 
               или None если практик нет
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
            FROM yoga_practices 
            WHERE weekday = %s OR weekday IS NULL
            ORDER BY RANDOM()
            LIMIT 1
        ''', (weekday,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result
        
    except Exception as e:
        print(f"Ошибка получения случайной йога практики для дня недели {weekday}: {e}")
        if conn:
            conn.close()
        return None

def search_yoga_practices(search_term: str) -> list:
    """Ищет йога практики по названию или описанию.
    
    Args:
        search_term: поисковый запрос
        
    Returns:
        list: Список кортежей (practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        search_pattern = f'%{search_term}%'
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
            FROM yoga_practices 
            WHERE title ILIKE %s OR description ILIKE %s OR channel_name ILIKE %s
            ORDER BY created_at DESC
        ''', (search_pattern, search_pattern, search_pattern))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка поиска йога практик: {e}")
        if conn:
            conn.close()
        return []

def update_yoga_practice(practice_id: int, title: str = None, video_url: str = None, 
                        time_practices: int = None, channel_name: str = None, 
                        description: str = None, my_description: str = None, intensity: str = None, weekday: int = None) -> bool:
    """Обновляет данные йога практики.
    
    Args:
        practice_id: ID практики
        title: новое название видео (опционально)
        video_url: новая ссылка на видео (опционально)
        time_practices: новая длительность в минутах (опционально)
        channel_name: новое название канала (опционально)
        description: новое описание (опционально)
        my_description: новое мое описание (опционально)
        intensity: новая интенсивность (опционально)
        weekday: новый день недели (1=понедельник, 7=воскресенье, None=любой день)
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Формируем SQL запрос динамически на основе переданных параметров
        update_fields = []
        params = []
        
        if title is not None:
            update_fields.append('title = %s')
            params.append(title)
        if video_url is not None:
            update_fields.append('video_url = %s')
            params.append(video_url)
        if time_practices is not None:
            update_fields.append('time_practices = %s')
            params.append(time_practices)
        if channel_name is not None:
            update_fields.append('channel_name = %s')
            params.append(channel_name)
        if description is not None:
            # Обрезаем description до 500 символов (ограничение БД)
            if len(description) > 500:
                description = description[:500]
            update_fields.append('description = %s')
            params.append(description)
        if my_description is not None:
            # Декодируем маркеры переноса строк, чтобы при обновлении сразу хранить готовый текст
            update_fields.append('my_description = %s')
            params.append(_decode_my_description(my_description))
        if intensity is not None:
            update_fields.append('intensity = %s')
            params.append(intensity)
        if weekday is not None:
            update_fields.append('weekday = %s')
            params.append(weekday)
        
        if not update_fields:
            print("Не указаны поля для обновления")
            return False
        
        update_fields.append('updated_at = CURRENT_TIMESTAMP')
        params.append(practice_id)
        
        sql = f'''
            UPDATE yoga_practices 
            SET {', '.join(update_fields)}
            WHERE practices_id = %s
        '''
        
        cursor.execute(sql, params)
        
        if cursor.rowcount == 0:
            print(f"Йога практика с ID {practice_id} не найдена")
            return False
        
        conn.commit()
        conn.close()
        print(f"Йога практика {practice_id} обновлена")
        return True
        
    except Exception as e:
        print(f"Ошибка обновления йога практики {practice_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def delete_yoga_practice(practice_id: int) -> bool:
    """Удаляет йога практику из базы данных.
    
    Args:
        practice_id: ID практики
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM yoga_practices WHERE practices_id = %s', (practice_id,))
        
        if cursor.rowcount == 0:
            print(f"Йога практика с ID {practice_id} не найдена")
            return False
        
        conn.commit()
        conn.close()
        print(f"Йога практика {practice_id} удалена из базы данных")
        return True
        
    except Exception as e:
        print(f"Ошибка удаления йога практики {practice_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_random_yoga_practice() -> tuple:
    """Получает случайную йога практику.
    
    Returns:
        tuple: (practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at) 
               или None если практик нет
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, weekday, created_at, updated_at
            FROM yoga_practices 
            ORDER BY RANDOM()
            LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        return result
        
    except Exception as e:
        print(f"Ошибка получения случайной йога практики: {e}")
        if conn:
            conn.close()
        return None

def get_practice_count() -> int:
    """Получает общее количество йога практик в базе данных.
    
    Returns:
        int: Количество практик
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM yoga_practices')
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0
        
    except Exception as e:
        print(f"Ошибка получения количества йога практик: {e}")
        if conn:
            conn.close()
        return 0

def get_yoga_practice_by_weekday_order(weekday: int, day_number: int) -> tuple:
    """Получает йога практику для определенного дня недели по порядку.
    
    Логика выбора:
    - При старте пользователя (неделя 0) отправляется практика с наименьшим ID для данного дня недели
    - Каждую следующую неделю отправляется следующая практика по возрастанию ID
    - При достижении максимального ID цикл начинается заново
    
    Args:
        weekday: день недели (1=понедельник, 7=воскресенье)
        day_number: номер дня пользователя (начиная с 1)
        
    Returns:
        tuple: (practices_id, title, video_url, time_practices, channel_name, description, my_description, intensity, weekday, created_at, updated_at) 
               или None если практик нет
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Получаем все практики для данного дня недели, отсортированные по ID
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, my_description, intensity, weekday, created_at, updated_at
            FROM yoga_practices 
            WHERE weekday = %s
            ORDER BY practices_id
        ''', (weekday,))
        
        practices = cursor.fetchall()
        conn.close()
        
        if not practices:
            print(f"Нет практик для дня недели {weekday}")
            return None
        
        # Вычисляем номер недели пользователя (0, 1, 2, 3...)
        # Дни 1-7 = неделя 0, дни 8-14 = неделя 1, дни 15-21 = неделя 2 и т.д.
        week_number = (day_number - 1) // 7
        
        # Выбираем практику по номеру недели с циклическим повторением
        # Каждую неделю берем следующую практику по возрастанию ID
        # При достижении максимального ID начинаем заново
        practice_index = week_number % len(practices)
        return _decode_practice_row(practices[practice_index])
        
    except Exception as e:
        print(f"Ошибка получения практики по порядку для дня недели {weekday}, день {day_number}: {e}")
        if conn:
            conn.close()
        return None


def get_yoga_practice_by_challenge_order(challenge_start_id: int, day_number: int):
    """Возвращает практику для режима челленджа: все практики по возрастанию id, день N — N-я от старта, цикл с id=1 после конца.
    
    Args:
        challenge_start_id: id практики, с которой начинается челлендж
        day_number: номер дня (1, 2, 3, ...)
        
    Returns:
        tuple: (practices_id, title, video_url, ...) или None
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT practices_id, title, video_url, time_practices, channel_name, description, my_description, intensity, weekday, created_at, updated_at
            FROM yoga_practices
            ORDER BY practices_id
        ''')
        practices = cursor.fetchall()
        conn.close()
        if not practices:
            return None
        # Найти индекс первой практики с id >= challenge_start_id
        start_index = 0
        for i, row in enumerate(practices):
            if row[0] >= challenge_start_id:
                start_index = i
                break
        # День N → индекс (start_index + (N - 1)) % len(practices)
        position = (start_index + (day_number - 1)) % len(practices)
        return _decode_practice_row(practices[position])
    except Exception as e:
        print(f"Ошибка get_yoga_practice_by_challenge_order({challenge_start_id}, {day_number}): {e}")
        if conn:
            conn.close()
        return None


def get_practice_count_by_weekday(weekday: int) -> int:
    """Получает количество практик для определенного дня недели.
    
    Args:
        weekday: день недели (1=понедельник, 7=воскресенье)
        
    Returns:
        int: Количество практик для данного дня недели
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*)
            FROM yoga_practices 
            WHERE weekday = %s
        ''', (weekday,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0
        
    except Exception as e:
        print(f"Ошибка получения количества практик для дня недели {weekday}: {e}")
        if conn:
            conn.close()
        return 0

# --- Функции для бонусных практик ---

def add_bonus_practice(parent_practice_id: int, title: str, video_url: str, time_practices: int,
                       channel_name: str, description: str = None, my_description: str = None,
                       intensity: str = None) -> bool:
    """Добавляет бонусную практику, которая отправляется вместе с основной.
    
    Args:
        parent_practice_id: ID основной практики, к которой привязана бонусная
        title: название видео
        video_url: ссылка на видео
        time_practices: длительность видео
        channel_name: название канала
        description: описание (опционально)
        my_description: мое описание (опционально)
        intensity: интенсивность (опционально)
        
    Returns:
        bool: True если операция прошла успешно, иначе False
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Переводим маркеры /n в реальные переводы строк перед сохранением
        my_description = _decode_my_description(my_description)
        
        # Обрезаем description до 500 символов (ограничение БД)
        if description and len(description) > 500:
            description = description[:500]
        
        cursor.execute('''
            INSERT INTO bonus_practices (
                parent_practice_id, title, video_url, time_practices, channel_name,
                description, my_description, intensity
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            parent_practice_id, title, video_url, time_practices, channel_name,
            description, my_description, intensity
        ))
        
        conn.commit()
        conn.close()
        print(f"Бонусная практика добавлена к {parent_practice_id}: {title}")
        return True
        
    except psycopg2.IntegrityError:
        print(f"Бонусное видео с URL {video_url} уже существует")
        if conn:
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print(f"Ошибка добавления бонусной практики: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def get_bonus_practices_by_parent(parent_practice_id: int) -> list:
    """Возвращает бонусные практики, привязанные к основной.
    
    Args:
        parent_practice_id: ID основной практики
        
    Returns:
        list: Список кортежей с данными бонусных практик
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT bonus_id, parent_practice_id, title, video_url, time_practices,
                   channel_name, description, my_description, intensity,
                   created_at, updated_at
            FROM bonus_practices
            WHERE parent_practice_id = %s
            ORDER BY bonus_id
        ''', (parent_practice_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [_decode_bonus_practice_row(row) for row in results]
        
    except Exception as e:
        print(f"Ошибка получения бонусных практик для {parent_practice_id}: {e}")
        if conn:
            conn.close()
        return []


def delete_bonus_practice(bonus_id: int) -> bool:
    """Удаляет бонусную практику.
    
    Args:
        bonus_id: ID бонусной практики
        
    Returns:
        bool: True если удалено, False при ошибке
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM bonus_practices WHERE bonus_id = %s', (bonus_id,))
        
        if cursor.rowcount == 0:
            print(f"Бонусная практика {bonus_id} не найдена")
            return False
        
        conn.commit()
        conn.close()
        print(f"Бонусная практика {bonus_id} удалена")
        return True
        
    except Exception as e:
        print(f"Ошибка удаления бонусной практики {bonus_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_bonus_practice_count() -> int:
    """Возвращает общее количество бонусных практик."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM bonus_practices')
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0
        
    except Exception as e:
        print(f"Ошибка получения количества бонусных практик: {e}")
        if conn:
            conn.close()
        return 0

# Вспомогательные функции для работы с днями недели

def weekday_to_name(weekday: int) -> str:
    """Конвертирует номер дня недели в название.
    
    Args:
        weekday: номер дня недели (1-7)
        
    Returns:
        str: Название дня недели на русском языке
    """
    weekdays = {
        1: "Понедельник",
        2: "Вторник", 
        3: "Среда",
        4: "Четверг",
        5: "Пятница",
        6: "Суббота",
        7: "Воскресенье"
    }
    return weekdays.get(weekday, "Неизвестный день")

def name_to_weekday(weekday_name: str) -> int:
    """Конвертирует название дня недели в номер.
    
    Args:
        weekday_name: название дня недели (на русском)
        
    Returns:
        int: Номер дня недели (1-7) или None если не найден
    """
    weekdays = {
        "понедельник": 1,
        "вторник": 2,
        "среда": 3,
        "четверг": 4,
        "пятница": 5,
        "суббота": 6,
        "воскресенье": 7,
        "пн": 1,
        "вт": 2,
        "ср": 3,
        "чт": 4,
        "пт": 5,
        "сб": 6,
        "вс": 7
    }
    return weekdays.get(weekday_name.lower().strip())

def get_current_weekday() -> int:
    """Получает текущий день недели.
    
    Returns:
        int: Номер текущего дня недели (1-7)
    """
    # datetime.now() нужно вызывать в правильной таймзоне, иначе при UTC сдвиге день недели собьётся
    tz = ZoneInfo(DEFAULT_TZ)
    # datetime.weekday() возвращает 0=понедельник, 6=воскресенье, поэтому добавляем 1 для совместимости с нашей логикой
    return datetime.now(tz).weekday() + 1

def get_weekday_statistics() -> dict:
    """Получает статистику по дням недели.
    
    Returns:
        dict: Словарь с количеством практик для каждого дня недели
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT weekday, COUNT(*) as count
            FROM yoga_practices 
            WHERE weekday IS NOT NULL
            GROUP BY weekday
            ORDER BY weekday
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        stats = {}
        for weekday, count in results:
            stats[weekday_to_name(weekday)] = count
        
        return stats
        
    except Exception as e:
        print(f"Ошибка получения статистики по дням недели: {e}")
        if conn:
            conn.close()
        return {}

# Функции для логирования отправленных практик

def log_practice_sent(user_id: int, practice_id: int, day_number: int) -> bool:
    """Логирует отправку практики пользователю.
    
    Args:
        user_id: ID пользователя
        practice_id: ID практики
        day_number: номер дня пользователя
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO practice_logs (user_id, practice_id, day_number)
            VALUES (%s, %s, %s)
        ''', (user_id, practice_id, day_number))
        
        conn.commit()
        conn.close()
        print(f"Практика {practice_id} залогирована для пользователя {user_id}, день {day_number}")
        return True
        
    except Exception as e:
        print(f"Ошибка логирования практики {practice_id} для пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_user_practice_history(user_id: int, limit: int = 10) -> list:
    """Получает историю отправленных практик пользователю.
    
    Args:
        user_id: ID пользователя
        limit: максимальное количество записей (по умолчанию 10)
        
    Returns:
        list: Список кортежей (log_id, practice_id, sent_at, day_number, title, video_url)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT pl.log_id, pl.practice_id, pl.sent_at, pl.day_number, 
                   yp.title, yp.video_url
            FROM practice_logs pl
            JOIN yoga_practices yp ON pl.practice_id = yp.practices_id
            WHERE pl.user_id = %s
            ORDER BY pl.sent_at DESC
            LIMIT %s
        ''', (user_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения истории практик пользователя {user_id}: {e}")
        if conn:
            conn.close()
        return []

def get_practice_sent_count(practice_id: int) -> int:
    """Получает количество отправок конкретной практики.
    
    Args:
        practice_id: ID практики
        
    Returns:
        int: Количество отправок
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*)
            FROM practice_logs 
            WHERE practice_id = %s
        ''', (practice_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0
        
    except Exception as e:
        print(f"Ошибка получения количества отправок практики {practice_id}: {e}")
        if conn:
            conn.close()
        return 0


def mark_practice_completed_today(user_id: int) -> bool:
    """Отмечает последнюю отправленную практику пользователя (без completed_at) как выполненную.
    Returns True если запись найдена и обновлена."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE practice_logs SET completed_at = CURRENT_TIMESTAMP
            WHERE log_id = (
                SELECT log_id FROM practice_logs
                WHERE user_id = %s AND completed_at IS NULL
                ORDER BY sent_at DESC LIMIT 1
            )
        ''', (user_id,))
        ok = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return ok
    except Exception as e:
        print(f"Ошибка mark_practice_completed_today для {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def get_completed_count(user_id: int) -> int:
    """Количество практик, отмеченных как выполненные (completed_at IS NOT NULL)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM practice_logs WHERE user_id = %s AND completed_at IS NOT NULL
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        print(f"Ошибка get_completed_count для {user_id}: {e}")
        if conn:
            conn.close()
        return 0


def get_similar_result_percent(user_id: int, bucket_size: int = 5, min_received: int = 5):
    """Возвращает процент пользователей с таким же результатом по бакету процента выполнения.

    Результат пользователя = completed / user_days * 100.
    «Такие же» = пользователи с user_days >= min_received, чьи результаты попали в тот же
    бакет шириной bucket_size (например, 50-54 для bucket_size=5).

    Returns:
        float | None: процент «таких же» пользователей (0..100) или None, если данных пока мало.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT COALESCE(user_days, 0) FROM users WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        user_days = int(row[0])
        if user_days < min_received or user_days <= 0:
            conn.close()
            return None

        cursor.execute('''
            SELECT COUNT(*) FROM practice_logs
            WHERE user_id = %s AND completed_at IS NOT NULL
        ''', (user_id,))
        completed_row = cursor.fetchone()
        user_completed = int(completed_row[0]) if completed_row else 0
        user_percent = (user_completed * 100.0) / user_days
        user_bucket = int(user_percent // bucket_size)

        cursor.execute('''
            WITH completed_by_user AS (
                SELECT user_id, COUNT(*) AS completed_cnt
                FROM practice_logs
                WHERE completed_at IS NOT NULL
                GROUP BY user_id
            ),
            eligible AS (
                SELECT u.user_id,
                       u.user_days,
                       COALESCE(c.completed_cnt, 0) AS completed_cnt
                FROM users u
                LEFT JOIN completed_by_user c ON c.user_id = u.user_id
                WHERE COALESCE(u.is_blocked, FALSE) = FALSE
                  AND COALESCE(u.user_days, 0) >= %s
            ),
            stats AS (
                SELECT
                    COUNT(*) AS total_cnt,
                    SUM(
                        CASE
                            WHEN FLOOR((completed_cnt * 100.0 / user_days) / %s) = %s THEN 1
                            ELSE 0
                        END
                    ) AS same_cnt
                FROM eligible
            )
            SELECT total_cnt, same_cnt FROM stats
        ''', (min_received, bucket_size, user_bucket))

        totals = cursor.fetchone()
        conn.close()
        if not totals:
            return None
        total_cnt = int(totals[0] or 0)
        same_cnt = int(totals[1] or 0)
        if total_cnt == 0:
            return None
        return (same_cnt * 100.0) / total_cnt

    except Exception as e:
        logger.error(f"Ошибка get_similar_result_percent для {user_id}: {e}")
        if conn:
            conn.close()
        return None


def reset_user_progress(user_id: int) -> bool:
    """Сбрасывает прогресс: user_days = 0, completed_at = NULL по всем логам пользователя. program_position не меняется."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET user_days = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s', (user_id,))
        if cursor.rowcount == 0:
            conn.close()
            return False
        cursor.execute('UPDATE practice_logs SET completed_at = NULL WHERE user_id = %s', (user_id,))
        conn.commit()
        conn.close()
        print(f"Прогресс пользователя {user_id} сброшен")
        return True
    except Exception as e:
        print(f"Ошибка reset_user_progress для {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def clear_all_yoga_practices() -> bool:
    """Удаляет все йога практики из базы данных.
    
    ВНИМАНИЕ: Эта операция удаляет ВСЕ практики из таблицы yoga_practices.
    Также автоматически удаляются все связанные записи из practice_logs 
    благодаря ON DELETE CASCADE.
    
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Сначала получаем количество записей для информации
        cursor.execute('SELECT COUNT(*) FROM yoga_practices')
        count_before = cursor.fetchone()[0]
        
        # Удаляем все записи из таблицы
        # Используем DELETE вместо TRUNCATE, чтобы сохранить структуру таблицы
        # и не нарушить работу автоинкремента (SERIAL)
        cursor.execute('DELETE FROM yoga_practices')
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"✅ Успешно удалено {deleted_count} практик из базы данных (было {count_before})")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка очистки таблицы yoga_practices: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


# --- Функции для массовых рассылок ---

def get_next_broadcast_batch_id() -> int:
    """Возвращает следующий номер партии рассылки (для группировки сообщений одной рассылки)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(MAX(broadcast_batch_id), 0) + 1 FROM broadcast_messages')
        batch_id = cursor.fetchone()[0]
        conn.close()
        return batch_id
    except Exception as e:
        print(f"Ошибка получения следующего broadcast_batch_id: {e}")
        if conn:
            conn.close()
        return 1


def save_broadcast_message(broadcast_batch_id: int, user_id: int, chat_id: int, message_id: int,
                          message_type: str, message_text: str = None,
                          photo_file_id: str = None) -> bool:
    """Сохраняет информацию об отправленном сообщении рассылки.

    Args:
        broadcast_batch_id: номер партии рассылки (одна рассылка = один batch_id)
        user_id: ID пользователя
        chat_id: ID чата
        message_id: ID отправленного сообщения в Telegram
        message_type: тип сообщения ('text' или 'photo')
        message_text: текст сообщения или подпись к фото (опционально)
        photo_file_id: file_id фото (опционально)

    Returns:
        bool: True если успешно, False при ошибке
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO broadcast_messages (broadcast_batch_id, user_id, chat_id, message_id, message_type, message_text, photo_file_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (broadcast_batch_id, user_id, chat_id, message_id, message_type, message_text, photo_file_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка сохранения сообщения рассылки: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def get_latest_broadcast_messages() -> list:
    """Возвращает все сообщения последней рассылки.

    Returns:
        list: Список кортежей (user_id, chat_id, message_id, message_type, message_text, photo_file_id)
              или пустой список, если рассылок нет.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(broadcast_batch_id) FROM broadcast_messages')
        row = cursor.fetchone()
        if not row or row[0] is None:
            conn.close()
            return []
        batch_id = row[0]
        cursor.execute('''
            SELECT user_id, chat_id, message_id, message_type, message_text, photo_file_id
            FROM broadcast_messages
            WHERE broadcast_batch_id = %s
            ORDER BY id
        ''', (batch_id,))
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        print(f"Ошибка получения последней рассылки: {e}")
        if conn:
            conn.close()
        return []


def get_latest_broadcast_meta() -> tuple:
    """Возвращает тип и контент последней рассылки (для подсказки при редактировании).

    Returns:
        tuple: (message_type, message_text, photo_file_id) или (None, None, None) если рассылок нет.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT message_type, message_text, photo_file_id
            FROM broadcast_messages
            ORDER BY broadcast_batch_id DESC, id
            LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()
        if row:
            return (row[0], row[1], row[2])
        return (None, None, None)
    except Exception as e:
        print(f"Ошибка получения мета последней рассылки: {e}")
        if conn:
            conn.close()
        return (None, None, None)


def delete_latest_broadcast() -> bool:
    """Удаляет из БД все записи последней рассылки (по максимальному broadcast_batch_id).

    Returns:
        bool: True если удалено, False при ошибке или если нечего удалять.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT MAX(broadcast_batch_id) FROM broadcast_messages')
        row = cursor.fetchone()
        if not row or row[0] is None:
            conn.close()
            return False
        batch_id = row[0]
        cursor.execute('DELETE FROM broadcast_messages WHERE broadcast_batch_id = %s', (batch_id,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        print(f"Удалено {deleted_count} записей рассылки (batch_id={batch_id}) из БД")
        return True
    except Exception as e:
        print(f"Ошибка удаления последней рассылки из БД: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

