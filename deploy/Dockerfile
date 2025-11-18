# Используем официальный Python образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем переменные окружения по умолчанию
ENV PYTHONPATH=/app
ENV DEFAULT_TZ=Europe/Moscow

# Копируем код приложения
COPY app/ ./app/
COPY data/ ./data/

# Создаем пользователя для безопасности
RUN useradd --create-home --shell /bin/bash botuser && \
    chown -R botuser:botuser /app
USER botuser

# Открываем порт (хотя для Telegram бота он не нужен, но может пригодиться для health checks)
EXPOSE 8080

# Запускаем бота
CMD ["python", "-m", "app.main"]
