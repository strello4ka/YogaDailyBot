import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Обязательные/основные переменные
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DEFAULT_TZ: str = os.getenv("DEFAULT_TZ", "Europe/Moscow")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


def get_db_config() -> dict:
    """Возвращает конфиг подключения к PostgreSQL из env.

    Ожидаемые переменные: POSTGRESQL_HOST, POSTGRESQL_PORT, POSTGRESQL_USER,
    POSTGRESQL_PASSWORD, POSTGRESQL_DBNAME
    """
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


