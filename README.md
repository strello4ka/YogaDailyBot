# YogaDailyBot

Telegram бот с йога-практиками, который работает в Railway и использует Railway Postgres.

## 🎯 Описание

YogaDailyBot помогает пользователям практиковать регулярно: в режиме Daily бот присылает практики по расписанию, а в режиме By mood подбирает практику по текущему запросу пользователя. Бот работает через Telegram long polling, хранит данные в PostgreSQL и деплоится в Railway.

## 🚀 Возможности

- ✅ **Daily режим** - ежедневная отправка практик в выбранное время
- ✅ **By mood режим** - подбор практики по настроению/запросу без расписания
- ✅ **Персонализация** - выбор режима, времени и паузы рассылки
- ✅ **Прогресс** - отслеживание выполненных практик
- ✅ **Админ-рассылки** - массовые сообщения пользователям
- ✅ **Railway Postgres** - рабочая база данных в Railway

## 🛠️ Технологии

- **Python 3.11**
- **python-telegram-bot** - для работы с Telegram API
- **PostgreSQL** - облачная база данных
- **psycopg2** - драйвер для PostgreSQL
- **APScheduler** - планировщик задач
- **Railway** - production hosting
- **Dockerfile** - production build для Railway

## 📋 Требования

- Railway project с service `YogaDailyBot`
- Railway Postgres service
- Telegram Bot Token
- Для локального теста: Python 3.11 и `venv`

## 🔧 Локальная разработка и тестовый бот

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd YogaDailyBot
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка тестового окружения

Для локального тестового бота используйте отдельный env-файл, чтобы не смешивать тест и production:

```bash
cp test/env.test.example test/.env.test
```

Заполните `test/.env.test` тестовым токеном и тестовой/локальной БД:

```env
BOT_TOKEN=your_bot_token_here
DEFAULT_TZ=Europe/Moscow
LOG_LEVEL=INFO
POSTGRESQL_HOST=your-postgres-host
POSTGRESQL_PORT=5432
POSTGRESQL_USER=your_username
POSTGRESQL_PASSWORD=your_password
POSTGRESQL_DBNAME=your_database_name
POSTGRES_SSLMODE=require
```

### 5. Локальный запуск

```bash
ENV_FILE=test/.env.test python -m app.main
```

## 🚀 Production Deploy: Railway

Production окружение живёт в Railway:

- service `YogaDailyBot` собирается из корневого `Dockerfile`;
- service `Postgres` хранит рабочую БД;
- бот работает через long polling, публичный webhook URL не нужен.

### Railway Variables

В `Railway -> YogaDailyBot -> Variables` должны быть заданы:

```env
BOT_TOKEN=<production Telegram bot token>
DEFAULT_TZ=Europe/Moscow
LOG_LEVEL=INFO

POSTGRESQL_HOST=<Railway Postgres public/internal host>
POSTGRESQL_PORT=<Railway Postgres port>
POSTGRESQL_USER=<Railway Postgres user>
POSTGRESQL_PASSWORD=<Railway Postgres password>
POSTGRESQL_DBNAME=<Railway Postgres database>
POSTGRES_SSLMODE=require
```

### Как выкатывается production

1. Изменения попадают в ветку `main`.
2. Railway автоматически запускает новый deploy.
3. Проверяем `Deploy Logs`: должно быть `Application started`, без `Traceback`/`ERROR`.
4. Делаем smoke-test в Telegram: `/start`, выбор режима, сохранение времени/By mood.

## 📣 Одноразовая рассылка со старого бота

Для уведомления старых пользователей о переезде используется ручной скрипт:

```bash
tools/broadcast_old_bot_migration.py
```

Он:
- берёт получателей из последнего архива старых пользователей в Railway DB;
- отправляет только пользователям, у которых `is_blocked` не равен `true`;
- использует отдельную переменную `OLD_BOT_TOKEN`;
- не связан с Railway deploy и не запускается автоматически.

Dry-run без реальной отправки:

```bash
DATABASE_URL="<railway_postgres_url>" python tools/broadcast_old_bot_migration.py --limit 5
```

Тестовая отправка одному пользователю:

```bash
DATABASE_URL="<railway_postgres_url>" \
OLD_BOT_TOKEN="<old_bot_token>" \
python tools/broadcast_old_bot_migration.py --send --confirm SEND --user-id <telegram_user_id>
```

Массовая отправка:

```bash
DATABASE_URL="<railway_postgres_url>" \
OLD_BOT_TOKEN="<old_bot_token>" \
python tools/broadcast_old_bot_migration.py --send --confirm SEND
```

Отчёты сохраняются в `broadcast_reports/` и не коммитятся в git.

## 📊 Структура базы данных

### Таблица `users`
- `user_id` - ID пользователя в Telegram
- `chat_id` - ID чата
- `notify_time` - время уведомлений (HH:MM)
- `user_name` - имя пользователя
- `user_nickname` - username пользователя
- `user_days` - количество дней практики
- `bot_mode` - режим (`pending`, `daily`, `by_mood`)
- `daily_schedule_enabled` - включена ли ежедневная рассылка
- `is_paused` - пауза Daily-рассылки
- `created_at` - дата регистрации
- `updated_at` - дата последнего обновления

### Таблица `yoga_practices`
- `practices_id` - уникальный ID практики
- `title` - название видео
- `video_url` - ссылка на YouTube
- `time_practices` - длительность в минутах
- `channel_name` - название канала
- `description` - описание видео
- `my_description` - дополнительное описание
- `intensity` - интенсивность (легкая/средняя/высокая)
- `weekday` - день недели (1-7, NULL для любого дня)
- `created_at` - дата добавления
- `updated_at` - дата последнего обновления

### Таблица `practice_logs`
- `log_id` - уникальный ID лога
- `user_id` - ID пользователя
- `practice_id` - ID практики
- `sent_at` - время отправки
- `day_number` - номер дня пользователя
- `completed_at` - дата отметки выполнения

### Таблица `by_mood_seen`
- `user_id` - ID пользователя
- `filter_key` - выбранный фильтр By mood
- `practice_id` - отправленная практика
- `sent_at` - дата отправки

## 🎮 Команды бота

### Команды для пользователей

- `/start` - запускает онбординг: знакомство с ботом и выбор режима.
- `/help` - показывает, куда написать по вопросам, ошибкам и идеям.
- Кнопка **«Пауза»** (reply-клавиатура в режиме Daily) — переключает паузу рассылки (нажать снова, чтобы возобновить). В паузе ежедневные практики не отправляются, прогресс сохраняется; если был активен челлендж, он завершается и после возобновления работает обычный режим.
- `/change_mode` - позволяет заново выбрать Daily или By mood.
- `/challenge <id>` - включает режим челленджа, где практики идут последовательно, начиная с указанного `id` практики (пример: `/challenge 54`).
- `/challenge_off` - выключает режим челленджа и возвращает обычную логику отправки практик.

### Служебные команды (в основном для разработки/тестов)

- `/test` - отправляет тестовую практику сразу, чтобы проверить работу рассылки.
- `/myid` - показывает техническую информацию пользователя (`user_id` и `chat_id`) для отладки.

### Админ-команды (доступны только администратору)

- `/secret` - запускает массовую рассылку всем пользователям (текст или фото с подписью).
- `/secret_delete` - удаляет последнюю массовую рассылку у пользователей.
- `/secret_edit` - редактирует текст/подпись последней массовой рассылки.

## 📈 Мониторинг

Бот автоматически логирует:
- Подключения к базе данных
- Отправку практик пользователям
- Ошибки и исключения
- Статистику использования

## 🔒 Безопасность

- Все пароли и токены хранятся в переменных окружения
- Подключение к PostgreSQL через SSL
- Валидация входных данных
- Логирование всех операций

## 🤝 Разработка

### Структура проекта

```
YogaDailyBot/
├── app/
│   ├── by_mood/       # By mood подбор практик
│   ├── handlers/      # Обработчики команд и кнопок
│   ├── schedule/      # Планировщик Daily-рассылки
│   ├── main.py        # Entrypoint
│   ├── keyboards.py   # Клавиатуры
│   └── config.py      # Конфигурация из env
├── data/
│   ├── db.py          # Основной модуль БД
│   └── postgres_db.py # PostgreSQL функции и миграции
├── test/              # Локальный тестовый запуск и тестовые шаблоны env
├── Dockerfile         # Railway production build
└── requirements.txt   # Python зависимости
```

### Добавление новых функций

1. Создайте обработчик в `app/handlers/`
2. Добавьте команду в `app/main.py`
3. При необходимости обновите базу данных
4. Протестируйте функциональность

## 🧹 Legacy deploy

Старый Kubernetes/Timeweb deploy удалён. Актуальный production-путь один: Railway auto deploy из `main`.

## 🧾 Закрытие Timeweb

После стабильной работы Railway:

1. Остановить старый бот workload/service в Timeweb.
2. Убедиться, что новая Railway DB является единственным рабочим источником данных.
3. Скачать закрывающие документы/счета, если они нужны.
4. Отключить автопродление услуг.
5. Проверить остаток баланса и вывести/использовать его по правилам Timeweb.
6. Удалить или заморозить старые облачные ресурсы.
7. Отвязать карту в разделе биллинга/способов оплаты.

Если в интерфейсе нет отвязки карты, нужно удалить автоплатежи/платёжный метод через поддержку Timeweb.

## 📞 Поддержка

Если у вас возникли вопросы или проблемы:

1. Проверьте логи бота
2. Убедитесь, что все переменные окружения настроены
3. Проверьте подключение к базе данных
4. Создайте issue в репозитории

## 📄 Лицензия

Этот проект распространяется под лицензией MIT.

---

**Удачной практики! 🧘‍♀️**
