# 🧘‍♀️ База данных YogaDailyBot

PostgreSQL база данных для хранения всех данных проекта YogaDailyBot.

## 🔗 Подключение к базе данных

### Настройки подключения
База данных находится на удаленном сервере PostgreSQL. Настройки подключения хранятся в файле `.env` и не должны попадать в публичную документацию.

### Переменные окружения
Создайте файл `.env` в корне проекта со следующими переменными:

```env
# Настройки PostgreSQL
POSTGRESQL_HOST=your_host
POSTGRESQL_PORT=5432
POSTGRESQL_USER=your_username
POSTGRESQL_PASSWORD=your_password
POSTGRESQL_DBNAME=yoga_club

# Настройки бота
BOT_TOKEN=your_bot_token
DEFAULT_TZ=Europe/Moscow
```

⚠️ **Важно**: Никогда не коммитьте файл `.env` в репозиторий! 

### Создание файла .env
1. Скопируйте переменные выше в новый файл `.env`
2. Заполните все значения своими данными
3. Убедитесь, что файл `.env` добавлен в `.gitignore`

### Для команды разработки
Создайте файл `.env.example` с placeholder'ами (без реальных значений) для других разработчиков:
```env
POSTGRESQL_HOST=your_host
POSTGRESQL_USER=your_username
POSTGRESQL_PASSWORD=your_password
# и т.д.
```

### Инициализация
База данных автоматически инициализируется при импорте модуля `data.postgres_db`:

```python
from data.postgres_db import create_tables
# Все таблицы создаются автоматически
```

## 📋 Структура таблиц

### 1. Таблица `users` - Пользователи

| Поле | Тип | Описание |
|------|-----|----------|
| `user_id` | BIGINT | Уникальный ID пользователя (PRIMARY KEY) |
| `chat_id` | BIGINT | ID чата в Telegram |
| `notify_time` | VARCHAR(5) | Время уведомлений в формате HH:MM |
| `user_name` | TEXT | Имя пользователя (опционально) |
| `user_phone` | TEXT | Телефон пользователя (опционально) |
| `user_days` | INTEGER | Счетчик дней пользователя (по умолчанию 0) |
| `user_week` | INTEGER | Текущая неделя пользователя (по умолчанию 1) |
| `onboarding_weekday` | INTEGER | День недели регистрации (1-7) |
| `created_at` | TIMESTAMP | Дата создания записи |
| `updated_at` | TIMESTAMP | Дата последнего обновления |

### 2. Таблица `yoga_practices` - Обычные практики

Таблица `yoga_practices` содержит следующие поля:

| Поле | Тип | Описание |
|------|-----|----------|
| `practices_id` | SERIAL | Уникальный ID практики (автоинкремент, PRIMARY KEY) |
| `title` | TEXT | Название видео |
| `video_url` | TEXT | Ссылка на YouTube видео (уникальная) |
| `time_practices` | INTEGER | Длительность видео в минутах |
| `channel_name` | TEXT | Название канала |
| `description` | TEXT | Описание видео (автоматически с YouTube) |
| `my_description` | TEXT | Мое описание (заполняется вручную) |
| `intensity` | TEXT | Интенсивность практики (легкая, средняя, высокая) |
| `weekday` | INTEGER | День недели (1=понедельник, 7=воскресенье, NULL=любой день) |
| `created_at` | TIMESTAMP | Дата добавления записи |
| `updated_at` | TIMESTAMP | Дата последнего обновления |

### 3. Таблица `newbie_practices` - Практики для новичков

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | SERIAL | Уникальный ID практики (автоинкремент, PRIMARY KEY) |
| `title` | TEXT | Название видео |
| `video_url` | TEXT | Ссылка на YouTube видео (уникальная) |
| `duration_minutes` | INTEGER | Длительность видео в минутах |
| `channel_name` | TEXT | Название канала |
| `description` | TEXT | Описание практики (опционально) |
| `number_practices` | INTEGER | Номер практики в программе (1-28, не уникальный) |
| `created_at` | TIMESTAMP | Дата добавления записи |
| `updated_at` | TIMESTAMP | Дата последнего обновления |

### 4. Таблица `practice_logs` - Логи отправленных практик

| Поле | Тип | Описание |
|------|-----|----------|
| `log_id` | SERIAL | Уникальный ID лога (автоинкремент, PRIMARY KEY) |
| `user_id` | BIGINT | ID пользователя (FOREIGN KEY) |
| `practice_id` | INTEGER | ID практики (FOREIGN KEY) |
| `sent_at` | TIMESTAMP | Дата и время отправки |
| `day_number` | INTEGER | Номер дня пользователя |

### 5. Таблица `user_suggestions` - Предложения пользователей

| Поле | Тип | Описание |
|------|-----|----------|
| `suggestion_id` | SERIAL | Уникальный ID предложения (автоинкремент, PRIMARY KEY) |
| `user_id` | BIGINT | ID пользователя (FOREIGN KEY) |
| `video_url` | TEXT | Ссылка на рекомендуемое видео |
| `comment` | TEXT | Комментарий пользователя (опционально) |
| `created_at` | TIMESTAMP | Дата создания записи |

### 📅 Дни недели

Поле `weekday` использует следующую нумерацию:
- `1` - Понедельник
- `2` - Вторник
- `3` - Среда
- `4` - Четверг
- `5` - Пятница
- `6` - Суббота
- `7` - Воскресенье
- `NULL` - Любой день (практика подходит для любого дня недели)

## 🚀 Использование

### Автоматическая инициализация

База данных автоматически инициализируется при импорте модуля `app.db`:

```python
from app.db import add_yoga_practice
# База данных уже создана и готова к использованию
```

## 🚀 Функции для работы с пользователями

### Управление пользователями

```python
from data.db import save_user_time, get_user_time, increment_user_days, get_user_days

# Сохранение пользователя с днем недели регистрации
save_user_time(user_id, chat_id, "09:00", "Имя", onboarding_weekday=1)

# Получение данных пользователя
user_data = get_user_time(user_id)
# Возвращает: (chat_id, notify_time, user_name, user_phone, user_days, user_week, onboarding_weekday)

# Увеличение счетчика дней
increment_user_days(user_id)

# Получение количества дней
days = get_user_days(user_id)
```

## 🆕 Функции для работы с практиками новичков

### Управление практиками новичков

```python
from data.db import add_newbie_practice, get_newbie_practice_by_number

# Добавление практики для новичков
add_newbie_practice(
    title="Первая практика",
    video_url="https://youtube.com/watch?v=...",
    duration_minutes=15,
    channel_name="Yoga Channel",
    description="Описание практики",
    number_practices=1  # Номер практики (1-28)
)

# Получение практик по номеру
practices = get_newbie_practice_by_number(1)  # Все практики с номером 1
```

### Основные функции

#### Добавление обычной практики

```python
from app.db import add_yoga_practice

success = add_yoga_practice(
    title="Утренняя йога для начинающих",
    video_url="https://www.youtube.com/watch?v=abc123",
    duration_minutes=15,
    channel_name="Yoga with Adriene",
    description="Простая утренняя практика",
    weekday=1  # Понедельник
)
```

#### Получение практик

```python
from app.db import (
    get_all_yoga_practices,
    get_yoga_practice_by_id,
    get_yoga_practice_by_url,
    get_yoga_practices_by_channel,
    get_yoga_practices_by_duration,
    get_yoga_practices_by_weekday,
    get_random_yoga_practice_by_weekday,
    search_yoga_practices,
    get_random_yoga_practice
)

# Все практики
practices = get_all_yoga_practices()

# По ID
practice = get_yoga_practice_by_id(1)

# По URL
practice = get_yoga_practice_by_url("https://www.youtube.com/watch?v=abc123")

# По каналу
practices = get_yoga_practices_by_channel("Yoga with Adriene")

# По длительности (до 20 минут)
practices = get_yoga_practices_by_duration(max_duration=20)

# По дню недели (понедельник)
practices = get_yoga_practices_by_weekday(1)

# Случайная практика для понедельника
practice = get_random_yoga_practice_by_weekday(1)

# Поиск по тексту
practices = search_yoga_practices("утренняя")

# Случайная практика
practice = get_random_yoga_practice()
```

#### Обновление практики

```python
from app.db import update_yoga_practice

success = update_yoga_practice(
    practice_id=1,
    title="Новое название",
    description="Новое описание",
    weekday=2  # Вторник
)
```

#### Удаление практики

```python
from app.db import delete_yoga_practice

success = delete_yoga_practice(practice_id=1)
```

#### Статистика

```python
from app.db import get_practice_count, get_weekday_statistics

count = get_practice_count()
print(f"Всего практик: {count}")

# Статистика по дням недели
weekday_stats = get_weekday_statistics()
for day, count in weekday_stats.items():
    print(f"{day}: {count} практик")
```

### Вспомогательные функции для дней недели

```python
from app.db import (
    weekday_to_name, name_to_weekday, get_current_weekday
)

# Конвертация номера в название
day_name = weekday_to_name(1)  # "Понедельник"

# Конвертация названия в номер
weekday_num = name_to_weekday("понедельник")  # 1
weekday_num = name_to_weekday("пн")  # 1

# Текущий день недели
current_day = get_current_weekday()  # 1-7
```

## 🛠️ Инструменты

### Тестирование

Запустите тест для проверки всех функций:

```bash
source venv/bin/activate
python test_yoga_db.py
```

### Тестирование логики новичков

Запустите тест для проверки новой логики:

```bash
source venv/bin/activate
python test_newbie_logic.py
```

### Массовое добавление практик

#### Обычные практики
```bash
source venv/bin/activate
python app/content/bulk_add_practices.py
```

#### Практики для новичков
```bash
source venv/bin/activate
python app/content/bulk_add_newbie_practices.py
```

### Интерактивное добавление

Используйте интерактивный скрипт для добавления практик:

```bash
source venv/bin/activate
python add_yoga_practice.py
```

## 📊 Индексы

Для оптимизации поиска созданы следующие индексы:

### Таблица `yoga_practices`
- `idx_video_url` - для быстрого поиска по URL видео
- `idx_channel_name` - для поиска по каналу
- `idx_duration` - для поиска по длительности
- `idx_weekday` - для поиска по дню недели

### Таблица `newbie_practices`
- `idx_newbie_practices_number` - для поиска по номеру практики
- `idx_newbie_practices_url` - для поиска по URL видео

### Таблица `users`
- `idx_user_id` - первичный ключ
- `idx_user_days` - для поиска пользователей по количеству дней

## 🔒 Ограничения

### Общие ограничения
- URL видео должен быть уникальным (нельзя добавить одно видео дважды)
- Длительность должна быть положительным числом
- Название видео и канала обязательны

### Ограничения по дням недели
- День недели должен быть от 1 до 7 (или NULL)
- `onboarding_weekday` должен быть от 1 до 7

### Ограничения для новичков
- `number_practices` должен быть от 1 до 28
- `user_days` отслеживает прогресс пользователя (0-28+)
- После 28-го дня пользователь переходит на обычную логику

## 📝 Примеры использования в боте

### Отправка практики для текущего дня недели

```python
from app.db import get_random_yoga_practice_by_weekday, get_current_weekday, weekday_to_name

def send_todays_practice(chat_id):
    current_day = get_current_weekday()
    practice = get_random_yoga_practice_by_weekday(current_day)
    
    if practice:
        day_name = weekday_to_name(current_day)
        message = f"""
🧘‍♀️ Практика на {day_name}:

📝 {practice[1]}
⏱️ {practice[3]} минут
📺 {practice[4]}
🔗 {practice[2]}
        """
        # Отправка сообщения пользователю
        bot.send_message(chat_id, message)
```

### Поиск практик по дню недели

```python
from app.db import get_yoga_practices_by_weekday, weekday_to_name

def find_monday_practices():
    # Практики для понедельника
    practices = get_yoga_practices_by_weekday(1)
    return practices
```

### Статистика по дням недели

```python
from app.db import get_weekday_statistics

def show_weekday_stats():
    stats = get_weekday_statistics()
    message = "📊 Статистика по дням недели:\n"
    for day, count in stats.items():
        message += f"• {day}: {count} практик\n"
    return message
```

### Поиск по ключевым словам

```python
from app.db import search_yoga_practices

def find_practices_by_keyword(keyword):
    practices = search_yoga_practices(keyword)
    return practices
```

### Отправка практики новичку

```python
from app.schedule.scheduler import send_newbie_practice
from data.db import get_user_time

def send_practice_to_newbie(user_id, chat_id):
    user_data = get_user_time(user_id)
    chat_id, notify_time, user_name, user_phone, user_days, user_week, onboarding_weekday = user_data
    
    if user_days <= 28:  # Новый пользователь
        new_day_number = user_days + 1
        await send_newbie_practice(context, user_id, chat_id, onboarding_weekday, new_day_number)
    else:  # Обычный пользователь
        # Логика для обычных пользователей
        pass
```

### Определение первой практики по дню регистрации

```python
def get_first_practice_number(onboarding_weekday):
    """
    Определяет номер первой практики на основе дня регистрации
    Воскресенье (7) → Практика #1
    Понедельник (1) → Практика #2
    И так далее...
    """
    return (onboarding_weekday % 7) + 1
```

## 🆕 Логика для новичков

### Первые 28 дней

Новые пользователи получают фиксированный набор практик в течение первых 28 дней:

1. **День регистрации определяет первую практику:**
   - Воскресенье → Практика #1 (отправляется в понедельник)
   - Понедельник → Практика #2 (отправляется во вторник)
   - Вторник → Практика #3 (отправляется в среду)
   - Среда → Практика #4 (отправляется в четверг)
   - Четверг → Практика #5 (отправляется в пятницу)
   - Пятница → Практика #6 (отправляется в субботу)
   - Суббота → Практика #7 (отправляется в воскресенье)

2. **После 28-го дня** пользователь переходит на обычную логику с практиками из таблицы `yoga_practices`

3. **Несколько практик в один день:** если в `number_practices` есть несколько записей, они отправляются с интервалом 1 минута в порядке возрастания `id`

### Поля для отслеживания

- `user_days` - счетчик дней пользователя (0-28+)
- `onboarding_weekday` - день недели регистрации (1-7)
- `number_practices` - номер практики в программе (1-28)

## 🎯 Интеграция с существующим ботом

База данных интегрирована в существующую структуру проекта:

- Использует PostgreSQL базу данных (`yoga_club`)
- Следует принципам именования и структуры
- Совместима с существующими функциями для работы с пользователями
- Поддерживает как обычные практики, так и специальную программу для новичков

## 🔧 Расширение функциональности

Для добавления новых функций можно:

1. Добавить новые поля в таблицу `yoga_practices`
2. Создать новые функции в `app/db.py`
3. Обновить индексы для оптимизации новых запросов
4. Добавить соответствующие тесты в `test_yoga_db.py`

## 📅 Планирование практик

Новое поле `weekday` позволяет:

- **Планировать практики** на определенные дни недели
- **Рекомендовать практики** в зависимости от текущего дня
- **Создавать расписания** для пользователей
- **Анализировать распределение** практик по дням недели
- **Персонализировать рекомендации** на основе предпочтений пользователей
