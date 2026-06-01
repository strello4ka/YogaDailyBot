import os
from urllib.parse import urlparse
from dotenv import load_dotenv

# Загружаем переменные окружения из выбранного .env файла
# ENV_FILE=.env.test — для тестового бота, иначе используется .env (прод)
env_file = os.getenv("ENV_FILE", ".env")
load_dotenv(env_file)

# Обязательные/основные переменные
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DEFAULT_TZ: str = os.getenv("DEFAULT_TZ", "Europe/Moscow")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


def get_database_url() -> str:
    """Строка подключения PostgreSQL, если задана DATABASE_URL."""
    return os.getenv("DATABASE_URL", "").strip()


def get_db_connection_label() -> str:
    """Краткая подпись БД для логов (без пароля)."""
    url = get_database_url()
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or "?"
        port = parsed.port or 5432
        dbname = (parsed.path or "/").lstrip("/") or "?"
        return f"{host}:{port}/{dbname}"
    host = os.getenv("POSTGRESQL_HOST") or "?"
    port = os.getenv("POSTGRESQL_PORT", "5432")
    dbname = os.getenv("POSTGRESQL_DBNAME") or "?"
    return f"{host}:{port}/{dbname}"


def get_db_config() -> dict:
    """Возвращает конфиг подключения к PostgreSQL из env.

    Приоритет: DATABASE_URL, иначе POSTGRESQL_HOST, POSTGRESQL_PORT,
    POSTGRESQL_USER, POSTGRESQL_PASSWORD, POSTGRESQL_DBNAME.
    """
    database_url = get_database_url()
    if database_url:
        return {"dsn": database_url}

    host = os.getenv("POSTGRESQL_HOST")
    port = int(os.getenv("POSTGRESQL_PORT", "5432"))
    user = os.getenv("POSTGRESQL_USER")
    password = os.getenv("POSTGRESQL_PASSWORD")
    dbname = os.getenv("POSTGRESQL_DBNAME")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
        "sslmode": os.getenv("POSTGRES_SSLMODE", "require"),
    }


