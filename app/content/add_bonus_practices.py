#!/usr/bin/env python3
"""
Скрипт для массового добавления бонусных практик из CSV файла.
"""

import sys
import os
import csv
from urllib.parse import urlparse, parse_qs

# Добавляем путь к корню проекта, чтобы импортировать data.db
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from app.config import get_db_connection_label  # noqa: E402
from data.db import (  # noqa: E402 - импортируем после настройки sys.path
    add_bonus_practice,
    get_bonus_practice_count,
    get_yoga_practice_by_id
)


def extract_video_id(url: str):
    """Проверяем, действительно ли ссылка ведет на YouTube, чтобы избежать мусора."""
    parsed_url = urlparse(url)

    if parsed_url.hostname in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            return parse_qs(parsed_url.query).get('v', [None])[0]
        if parsed_url.path.startswith('/embed/'):
            return parsed_url.path.split('/')[2]
    elif parsed_url.hostname == 'youtu.be':
        return parsed_url.path[1:]

    return None


def get_youtube_data(url: str):
    """Подтягиваем название, канал, описание и длительность с YouTube."""
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

        return {
            'title': info.get('title', 'Без названия'),
            'channel_name': info.get('uploader', 'Неизвестный канал'),
            'description': (info.get('description') or '')[:1000],
            'time_practices': (info.get('duration', 0) or 0) // 60,
        }
    except Exception as exc:
        print(f"❌ Ошибка получения данных с YouTube: {exc}")
        err = str(exc).lower()
        if 'not a bot' in err or 'sign in to confirm' in err:
            print(
                "💡 Добавьте в .env: YOUTUBE_COOKIES_BROWSER=chrome\n"
                "   (или export YOUTUBE_COOKIES_BROWSER=chrome в терминале)"
            )
        return None


def create_csv_template():
    """Генерируем шаблон CSV, чтобы можно было просто заполнить и загрузить."""
    csv_file = os.path.join(os.path.dirname(__file__), 'bonus_practices.csv')

    with open(csv_file, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['parent_practice_id', 'video_url', 'my_description', 'intensity'])
        writer.writerow(['1', 'https://www.youtube.com/watch?v=exampleBonus', 'Мягкое дополнение к основному занятию', 'Легкая'])
        writer.writerow(['3', 'https://youtu.be/exampleBonus2', 'Для тех, кому хочется добавить огня', 'Средняя'])
        writer.writerow(['5', 'https://www.youtube.com/watch?v=exampleBonus3', '', ''])

    print(f"✅ Создан шаблон файла: {csv_file}")
    print("📝 Заполните файл своими данными:")
    print("   - parent_practice_id: ID основной практики, к которой цепляем бонус")
    print("   - video_url: ссылка на YouTube видео")
    print("   - my_description: ваше описание (опционально)")
    print("   - intensity: интенсивность бонуса (опционально)")


def validate_parent_practice(practice_id_str: str, row_num: int):
    """Проверяем, что практика-родитель существует, иначе бонус повиснет в воздухе."""
    if not practice_id_str:
        print(f"❌ Строка {row_num}: не указан parent_practice_id")
        return None

    try:
        practice_id = int(practice_id_str)
    except ValueError:
        print(f"❌ Строка {row_num}: parent_practice_id должен быть числом")
        return None

    parent_practice = get_yoga_practice_by_id(practice_id)
    if not parent_practice:
        print(f"❌ Строка {row_num}: практика с ID {practice_id} не найдена")
        return None

    return practice_id


def process_csv_file(csv_file: str):
    """Проходим по CSV и загружаем бонусы в базу."""
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

            parent_practice_id = validate_parent_practice((row.get('parent_practice_id') or '').strip(), row_num)
            if not parent_practice_id:
                error_count += 1
                continue

            video_url = (row.get('video_url') or '').strip()
            if not video_url:
                print(f"❌ Строка {row_num}: не указана ссылка на бонусное видео")
                error_count += 1
                continue

            if not extract_video_id(video_url):
                print(f"❌ Строка {row_num}: ссылка должна вести на YouTube")
                error_count += 1
                continue

            my_description = (row.get('my_description') or '').strip()
            intensity = (row.get('intensity') or '').strip()

            print("📡 Получаем данные о бонусе с YouTube...")
            youtube_data = get_youtube_data(video_url)
            if not youtube_data:
                print(f"❌ Строка {row_num}: не получилось подтянуть данные с YouTube")
                error_count += 1
                continue

            print(f"   Название: {youtube_data['title']}")
            print(f"   Канал: {youtube_data['channel_name']}")
            print(f"   Длительность: {youtube_data['time_practices']} минут")

            success = add_bonus_practice(
                parent_practice_id=parent_practice_id,
                title=youtube_data['title'],
                video_url=video_url,
                time_practices=youtube_data['time_practices'],
                channel_name=youtube_data['channel_name'],
                description=youtube_data['description'],
                my_description=my_description or None,
                intensity=intensity or None
            )

            if success:
                print(f"✅ Строка {row_num}: бонус добавлен")
                added_count += 1
            else:
                print(f"❌ Строка {row_num}: ошибка записи в БД")
                error_count += 1

    print("\n" + "=" * 50)
    print("📊 Результаты обработки:")
    print(f"✅ Добавлено бонусов: {added_count}")
    print(f"❌ Ошибок: {error_count}")
    print(f"📈 Всего бонусов в базе: {get_bonus_practice_count()}")


def main():
    """Простое меню, чтобы можно было создать шаблон или загрузить бонусы."""
    print("💫 Массовое добавление бонусных практик")
    print("=" * 40)
    print(f"📡 База данных (из .env): {get_db_connection_label()}")
    if not os.environ.get('YOUTUBE_COOKIES_BROWSER', '').strip():
        print("⚠️  В .env нет YOUTUBE_COOKIES_BROWSER=chrome — YouTube может блокировать запросы.")

    while True:
        print("\nВыберите действие:")
        print("1. 📝 Создать шаблон CSV файла")
        print("2. 📁 Обработать CSV файл")
        print("3. 📊 Показать количество бонусов в базе")
        print("4. 🚪 Выйти")

        choice = input("\nВаш выбор (1-4): ").strip()

        if choice == '1':
            create_csv_template()
        elif choice == '2':
            csv_file = input("📁 Имя CSV файла (по умолчанию bonus_practices.csv): ").strip()
            if not csv_file:
                csv_file = os.path.join(os.path.dirname(__file__), 'bonus_practices.csv')
            process_csv_file(csv_file)
        elif choice == '3':
            count = get_bonus_practice_count()
            print(f"\n📊 Всего бонусных практик: {count}")
        elif choice == '4':
            print("👋 До встречи!")
            break
        else:
            print("❌ Неверный выбор. Попробуй снова.")


if __name__ == "__main__":
    main()

