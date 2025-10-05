import psycopg2
import psycopg2.extras
import os
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_db_config

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
                recommend TEXT,
                comment TEXT,
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
        
        # Создаем таблицу для фиксированного набора практик новичков
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS newbie_practices (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                video_url TEXT NOT NULL UNIQUE,
                duration_minutes INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                description TEXT,
                number_practices INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        
        # Миграция: добавляем поле user_week для отслеживания недели пользователя
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'user_week'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE users ADD COLUMN user_week INTEGER DEFAULT 1')
                print("✅ Колонка user_week добавлена в таблицу users")
        except Exception as e:
            print(f"⚠️ Ошибка добавления колонки user_week: {e}")
        
        # Миграция: добавляем поле onboarding_weekday для отслеживания дня недели регистрации
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'onboarding_weekday'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE users ADD COLUMN onboarding_weekday INTEGER')
                print("✅ Колонка onboarding_weekday добавлена в таблицу users")
        except Exception as e:
            print(f"⚠️ Ошибка добавления колонки onboarding_weekday: {e}")
        
        # Создаем индексы для быстрого поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_url ON yoga_practices(video_url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_channel_name ON yoga_practices(channel_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_duration ON yoga_practices(time_practices)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_weekday ON yoga_practices(weekday)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_intensity ON yoga_practices(intensity)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_practice_logs_user ON practice_logs(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_practice_logs_practice ON practice_logs(practice_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_suggestions_user ON user_suggestions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_suggestions_created ON user_suggestions(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_newbie_practices_number ON newbie_practices(number_practices)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_newbie_practices_url ON newbie_practices(video_url)')
        
        conn.commit()
        conn.close()
        print("PostgreSQL база данных инициализирована успешно")
        
    except Exception as e:
        print(f"Ошибка инициализации PostgreSQL базы данных: {e}")
        conn = None

def save_user_time(user_id: int, chat_id: int, notify_time: str, user_name: str = None, user_phone: str = None, onboarding_weekday: int = None) -> bool:
    """Сохраняет или обновляет время уведомлений пользователя.
    
    Args:
        user_id: ID пользователя
        chat_id: ID чата
        notify_time: время в формате HH:MM
        user_name: имя пользователя (опционально)
        user_phone: телефон пользователя (опционально)
        onboarding_weekday: день недели регистрации (1-7, опционально)
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Используем UPSERT (INSERT ... ON CONFLICT)
        cursor.execute('''
            INSERT INTO users (user_id, chat_id, notify_time, user_name, user_phone, user_days, onboarding_weekday)
            VALUES (%s, %s, %s, %s, %s, 0, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                chat_id = EXCLUDED.chat_id,
                notify_time = EXCLUDED.notify_time,
                user_name = EXCLUDED.user_name,
                user_phone = EXCLUDED.user_phone,
                user_days = 0,
                onboarding_weekday = COALESCE(EXCLUDED.onboarding_weekday, users.onboarding_weekday),
                updated_at = CURRENT_TIMESTAMP
        ''', (user_id, chat_id, notify_time, user_name, user_phone, onboarding_weekday))
        
        conn.commit()
        conn.close()
        print(f"Время пользователя {user_id} сохранено: {notify_time}")
        return True
        
    except Exception as e:
        print(f"Ошибка сохранения времени пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def save_user_practice_suggestion(user_id: int, video_url: str, comment: str = None) -> bool:
    """Сохраняет предложение практики от пользователя в отдельную таблицу.
    
    Args:
        user_id: ID пользователя, предложившего практику
        video_url: ссылка на рекомендуемое видео
        comment: комментарий пользователя к рекомендации (опционально)
        
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
        cursor.execute('''
            INSERT INTO user_suggestions (user_id, video_url, comment)
            VALUES (%s, %s, %s)
        ''', (user_id, video_url, comment))
        
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
        list: Список кортежей (suggestion_id, video_url, comment, created_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT suggestion_id, video_url, comment, created_at
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
        list: Список кортежей (suggestion_id, user_id, video_url, comment, created_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT suggestion_id, user_id, video_url, comment, created_at
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

def get_user_time(user_id: int) -> tuple:
    """Получает данные пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        tuple: (chat_id, notify_time, user_name, user_phone, user_days, user_week, onboarding_weekday) или (None, None, None, None, None, None, None) если пользователь не найден
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT chat_id, notify_time, user_name, user_phone, user_days, user_week, onboarding_weekday
            FROM users 
            WHERE user_id = %s
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result
        else:
            return (None, None, None, None, None, None, None)
            
    except Exception as e:
        print(f"Ошибка получения времени пользователя {user_id}: {e}")
        if conn:
            conn.close()
        return (None, None, None, None, None, None, None)

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
        list: Список кортежей (user_id, chat_id, notify_time, user_name, user_phone, user_days)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, chat_id, notify_time, user_name, user_phone, user_days
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
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, chat_id 
            FROM users 
            WHERE notify_time = %s
        ''', (notify_time,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения пользователей по времени {notify_time}: {e}")
        if conn:
            conn.close()
        return []

# Функции для работы с йога практиками

def add_yoga_practice(title: str, video_url: str, time_practices: int, channel_name: str, description: str = None, my_description: str = None, intensity: str = None, weekday: int = None) -> bool:
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
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO yoga_practices (title, video_url, time_practices, channel_name, description, my_description, intensity, weekday)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (title, video_url, time_practices, channel_name, description, my_description, intensity, weekday))
        
        conn.commit()
        conn.close()
        print(f"Йога практика добавлена: {title}")
        return True
        
    except psycopg2.IntegrityError:
        print(f"Видео с URL {video_url} уже существует в базе данных")
        if conn:
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print(f"Ошибка добавления йога практики: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

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
        
        return result
        
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
        
        return result
        
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
        
        return results
        
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
            update_fields.append('description = %s')
            params.append(description)
        if my_description is not None:
            update_fields.append('my_description = %s')
            params.append(my_description)
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
    
    Args:
        weekday: день недели (1=понедельник, 7=воскресенье)
        day_number: номер дня (начиная с 1)
        
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
        
        # Вычисляем индекс практики с учетом циклического повторения
        practice_index = (day_number - 1) % len(practices)
        return practices[practice_index]
        
    except Exception as e:
        print(f"Ошибка получения практики по порядку для дня недели {weekday}, день {day_number}: {e}")
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
    from datetime import datetime
    # datetime.weekday() возвращает 0=понедельник, 6=воскресенье
    # Нам нужно 1=понедельник, 7=воскресенье
    return datetime.now().weekday() + 1

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

# Функции для работы с практиками новичков

def add_newbie_practice(title: str, video_url: str, duration_minutes: int, channel_name: str, description: str = None, number_practices: int = 1) -> bool:
    """Добавляет новую практику для новичков в базу данных.
    
    Args:
        title: название видео
        video_url: ссылка на видео
        duration_minutes: длительность видео в минутах
        channel_name: название канала
        description: описание видео (опционально)
        number_practices: номер практики в программе (не уникальный)
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO newbie_practices (title, video_url, duration_minutes, channel_name, description, number_practices)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (title, video_url, duration_minutes, channel_name, description, number_practices))
        
        conn.commit()
        conn.close()
        print(f"Практика для новичков добавлена: {title}")
        return True
        
    except psycopg2.IntegrityError:
        print(f"Видео с URL {video_url} уже существует в базе данных новичков")
        if conn:
            conn.rollback()
            conn.close()
        return False
    except Exception as e:
        print(f"Ошибка добавления практики для новичков: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_newbie_practice_by_number(practice_number: int) -> list:
    """Получает все практики для новичков с указанным номером.
    
    Args:
        practice_number: номер практики
        
    Returns:
        list: Список кортежей (id, title, video_url, duration_minutes, channel_name, description, number_practices, created_at, updated_at)
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, video_url, duration_minutes, channel_name, description, number_practices, created_at, updated_at
            FROM newbie_practices 
            WHERE number_practices = %s
            ORDER BY id
        ''', (practice_number,))
        
        results = cursor.fetchall()
        conn.close()
        
        return results
        
    except Exception as e:
        print(f"Ошибка получения практик новичков с номером {practice_number}: {e}")
        if conn:
            conn.close()
        return []

def get_newbie_practice_count() -> int:
    """Получает общее количество практик для новичков в базе данных.
    
    Returns:
        int: Количество практик
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM newbie_practices')
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 0
        
    except Exception as e:
        print(f"Ошибка получения количества практик новичков: {e}")
        if conn:
            conn.close()
        return 0

def get_max_newbie_practice_number() -> int:
    """Получает максимальный номер практики для новичков.
    
    Returns:
        int: Максимальный номер практики
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT MAX(number_practices) FROM newbie_practices')
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result and result[0] else 0
        
    except Exception as e:
        print(f"Ошибка получения максимального номера практики новичков: {e}")
        if conn:
            conn.close()
        return 0

def update_user_week(user_id: int, new_week: int) -> bool:
    """Обновляет неделю пользователя.
    
    Args:
        user_id: ID пользователя
        new_week: новая неделя
        
    Returns:
        bool: True если операция успешна, False в случае ошибки
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET user_week = %s, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
        ''', (new_week, user_id))
        
        if cursor.rowcount == 0:
            print(f"Пользователь {user_id} не найден")
            return False
        
        conn.commit()
        conn.close()
        print(f"Неделя пользователя {user_id} обновлена на {new_week}")
        return True
        
    except Exception as e:
        print(f"Ошибка обновления недели пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def get_user_week(user_id: int) -> int:
    """Получает текущую неделю пользователя.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        int: Номер недели или 1 если пользователь не найден
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_week
            FROM users 
            WHERE user_id = %s
        ''', (user_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0] or 1
        else:
            return 1
            
    except Exception as e:
        print(f"Ошибка получения недели пользователя {user_id}: {e}")
        if conn:
            conn.close()
        return 1
