#!/usr/bin/env python3
"""
Скрипт для массового добавления йога практик из CSV файла.
"""

import sys
import os
import csv
import time
from urllib.parse import urlparse, parse_qs

# Добавляем путь к корневой папке проекта в sys.path
# Файл находится в app/content/, поэтому нужно подняться на 2 уровня выше до корня проекта
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from app.config import get_db_connection_label
from data.db import add_yoga_practice, get_practice_count, weekday_to_name


def extract_video_id(url):
    """Извлекает ID видео из YouTube URL."""
    parsed_url = urlparse(url)
    
    if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query).get('v', [None])[0]
        elif parsed_url.path.startswith('/embed/'):
            return parsed_url.path.split('/')[2]
    elif parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]
    
    return None


def get_youtube_data(url, delay_seconds=0):
    """Получает данные о видео с YouTube (cookies из .env: YOUTUBE_COOKIES_BROWSER или YOUTUBE_COOKIES_FILE)."""
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    try:
        import yt_dlp

        ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False}
        cookies_file = os.environ.get('YOUTUBE_COOKIES_FILE', '').strip()
        cookies_browser = os.environ.get('YOUTUBE_COOKIES_BROWSER', '').strip()
        if cookies_file and os.path.isfile(cookies_file):
            ydl_opts['cookiefile'] = cookies_file
        elif cookies_browser:
            ydl_opts['cookiesfrombrowser'] = (cookies_browser,)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration_seconds = info.get('duration', 0) or 0
        return {
            'title': info.get('title', 'Без названия'),
            'channel_name': info.get('uploader', 'Неизвестный канал'),
            'description': (info.get('description') or '')[:1000],
            'time_practices': duration_seconds // 60,
        }
    except Exception as e:
        print(f"❌ Ошибка получения данных с YouTube: {e}")
        err = str(e).lower()
        if 'not a bot' in err or 'sign in to confirm' in err:
            print(
                "💡 Добавьте в .env: YOUTUBE_COOKIES_BROWSER=chrome\n"
                "   (или export YOUTUBE_COOKIES_BROWSER=chrome в терминале)"
            )
        return None


def create_csv_template():
    """Создает шаблон CSV файла для заполнения."""
    csv_file = os.path.join(os.path.dirname(__file__), 'yoga_practices.csv')
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        # Заголовки
        writer.writerow([
            'video_url',
            'my_description', 
            'weekday'
        ])
        
        # Примеры строк
        writer.writerow([
            'https://www.youtube.com/watch?v=example1',
            'Утренняя практика для пробуждения',
            '1'
        ])
        writer.writerow([
            'https://www.youtube.com/watch?v=example2',
            'Вечерняя практика для расслабления',
            '5'
        ])
        writer.writerow([
            'https://www.youtube.com/watch?v=example3',
            'Практика для любого дня',
            ''
        ])
    
    print(f"✅ Создан шаблон файла: {csv_file}")
    print("📝 Заполните файл своими данными:")
    print("   - video_url: ссылка на YouTube видео")
    print("   - my_description: ваше описание (необязательно)")
    print("   - weekday: день недели (1-7, пусто для любого дня)")
    print("\n💡 Дни недели: 1=понедельник, 2=вторник, 3=среда, 4=четверг, 5=пятница, 6=суббота, 7=воскресенье")


def process_csv_file(csv_file):
    """Обрабатывает CSV файл и добавляет практики в базу данных."""
    
    if not os.path.exists(csv_file):
        print(f"❌ Файл {csv_file} не найден!")
        return
    
    print(f"📁 Обрабатываем файл: {csv_file}")
    print("=" * 50)
    
    added_count = 0
    error_count = 0
    
    with open(csv_file, 'r', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        
        for row_num, row in enumerate(reader, 1):
            print(f"\n📝 Обрабатываем строку {row_num}...")
            
            # Получаем данные из CSV
            video_url = row.get('video_url', '').strip()
            my_description = row.get('my_description', '').strip()
            weekday_str = row.get('weekday', '').strip()
            
            # Проверяем обязательные поля
            if not video_url:
                print(f"❌ Строка {row_num}: пропущена (нет ссылки)")
                error_count += 1
                continue
            
            # Проверяем YouTube ссылку
            video_id = extract_video_id(video_url)
            if not video_id:
                print(f"❌ Строка {row_num}: неверная ссылка на YouTube")
                error_count += 1
                continue
            
            # Обрабатываем день недели
            weekday = None
            if weekday_str:
                try:
                    weekday = int(weekday_str)
                    if weekday < 1 or weekday > 7:
                        print(f"❌ Строка {row_num}: неверный день недели (должен быть 1-7)")
                        error_count += 1
                        continue
                except ValueError:
                    print(f"❌ Строка {row_num}: неверный формат дня недели")
                    error_count += 1
                    continue
            
            # Получаем данные с YouTube (пауза снижает риск блокировки после нескольких строк)
            print(f"📡 Получаем данные с YouTube...")
            youtube_data = get_youtube_data(video_url, delay_seconds=2 if row_num > 1 else 0)
            if not youtube_data:
                print(f"❌ Строка {row_num}: не удалось получить данные с YouTube")
                error_count += 1
                continue
            
            # Показываем данные
            print(f"   Название: {youtube_data['title']}")
            print(f"   Канал: {youtube_data['channel_name']}")
            print(f"   Длительность: {youtube_data['time_practices']} минут")
            if my_description:
                print(f"   Мое описание: {my_description}")
            if weekday:
                print(f"   День недели: {weekday_to_name(weekday)}")
            else:
                print(f"   День недели: Любой день")
            
            # Добавляем в базу данных
            # Функция возвращает кортеж (success: bool, message: str)
            success, message = add_yoga_practice(
                title=youtube_data['title'],
                video_url=video_url,
                time_practices=youtube_data['time_practices'],
                channel_name=youtube_data['channel_name'],
                description=youtube_data['description'],
                my_description=my_description if my_description else None,
                weekday=weekday
            )
            
            if success:
                print(f"✅ Строка {row_num}: успешно добавлена")
                added_count += 1
            else:
                print(f"❌ Строка {row_num}: {message}")
                error_count += 1
    
    # Итоговая статистика
    print("\n" + "=" * 50)
    print("📊 Результаты обработки:")
    print(f"✅ Успешно добавлено: {added_count}")
    print(f"❌ Ошибок: {error_count}")
    print(f"📈 Всего практик в базе: {get_practice_count()}")


def main():
    """Главная функция."""
    print("🧘‍♀️ Массовое добавление йога практик")
    print("=" * 40)
    db_label = get_db_connection_label()
    print(f"📡 База данных (из .env): {db_label}")
    if not os.environ.get('YOUTUBE_COOKIES_BROWSER', '').strip():
        print("⚠️  В .env нет YOUTUBE_COOKIES_BROWSER=chrome — YouTube может блокировать запросы.")
    if db_label.startswith("81.19.136.130"):
        print(
            "⚠️  Похоже, в .env ещё старый сервер. Обновите подключение на Railway "
            "(DATABASE_PUBLIC_URL или POSTGRESQL_*)."
        )
    
    while True:
        print("\nВыберите действие:")
        print("1. 📝 Создать шаблон CSV файла")
        print("2. 📁 Обработать CSV файл")
        print("3. 📊 Показать статистику")
        print("4. 🚪 Выйти")
        
        choice = input("\nВаш выбор (1-4): ").strip()
        
        if choice == '1':
            create_csv_template()
        elif choice == '2':
            csv_file = input("📁 Введите имя CSV файла (по умолчанию yoga_practices.csv): ").strip()
            if not csv_file:
                csv_file = os.path.join(os.path.dirname(__file__), 'yoga_practices.csv')
            process_csv_file(csv_file)
        elif choice == '3':
            count = get_practice_count()
            print(f"\n📊 Всего практик в базе: {count}")
        elif choice == '4':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")


if __name__ == "__main__":
    main()
