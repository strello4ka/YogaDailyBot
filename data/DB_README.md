# 🧘‍♀️ База данных йога практик

База данных для хранения йога практик с YouTube, интегрированная в проект YogaDailyBot.

## 📋 Структура таблицы

Таблица `yoga_practices` содержит следующие поля:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Уникальный ID практики (автоинкремент) |
| `title` | TEXT | Название видео |
| `video_url` | TEXT | Ссылка на YouTube видео (уникальная) |
| `duration_minutes` | INTEGER | Длительность видео в минутах |
| `channel_name` | TEXT | Название канала |
| `description` | TEXT | Описание видео (опционально) |
| `weekday` | INTEGER | День недели (1=понедельник, 7=воскресенье, NULL=любой день) |
| `created_at` | TIMESTAMP | Дата добавления записи |
| `updated_at` | TIMESTAMP | Дата последнего обновления |

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

### Основные функции

#### Добавление практики

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

### Интерактивное добавление

Используйте интерактивный скрипт для добавления практик:

```bash
source venv/bin/activate
python add_yoga_practice.py
```

## 📊 Индексы

Для оптимизации поиска созданы следующие индексы:

- `idx_video_url` - для быстрого поиска по URL видео
- `idx_channel_name` - для поиска по каналу
- `idx_duration` - для поиска по длительности
- `idx_weekday` - для поиска по дню недели

## 🔒 Ограничения

- URL видео должен быть уникальным (нельзя добавить одно видео дважды)
- Длительность должна быть положительным числом
- Название видео и канала обязательны
- День недели должен быть от 1 до 7 (или NULL)

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

## 🎯 Интеграция с существующим ботом

База данных йога практик интегрирована в существующую структуру проекта:

- Использует ту же базу данных SQLite (`data/yogadaily.db`)
- Следует тем же принципам именования и структуры
- Совместима с существующими функциями для работы с пользователями

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
