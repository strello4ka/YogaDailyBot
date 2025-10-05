#!/usr/bin/env python3
"""
Скрипт для массового добавления йога практик для новичков из CSV файла.
"""

import sys
import os
import csv
from urllib.parse import urlparse, parse_qs

# Добавляем путь к корневой папке проекта в sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from data.db import add_newbie_practice, get_newbie_practice_count, get_max_newbie_practice_number


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


def get_youtube_data(url):
    """Получает данные о видео с YouTube."""
    try:
        import yt_dlp
        
        # Настройки для yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Получаем информацию о видео
            info = ydl.extract_info(url, download=False)
            
            # Извлекаем данные
            title = info.get('title', 'Без названия')
            channel_name = info.get('uploader', 'Неизвестный канал')
            description = info.get('description', '')[:1000]  # Ограничиваем длину описания
            duration_seconds = info.get('duration', 0)
            duration_minutes = duration_seconds // 60 if duration_seconds else 0
            
            return {
                'title': title,
                'channel_name': channel_name,
                'description': description,
                'duration_minutes': duration_minutes
            }
        
    except Exception as e:
        print(f"❌ Ошибка получения данных с YouTube: {e}")
        return None


def create_csv_template():
    """Создает шаблон CSV файла для заполнения."""
    csv_file = os.path.join(os.path.dirname(__file__), 'newbie_practices.csv')
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        # Заголовки
        writer.writerow([
            'video_url',
            'description', 
            'number_practices'
        ])
        
        # Примеры строк
        writer.writerow([
            'https://www.youtube.com/watch?v=example1',
            'Первая практика для новичков - основы дыхания',
            '1'
        ])
        writer.writerow([
            'https://www.youtube.com/watch?v=example2',
            'Вторая практика - простые асаны',
            '1'
        ])
        writer.writerow([
            'https://www.youtube.com/watch?v=example3',
            'Третья практика - растяжка',
            '2'
        ])
    
    print(f"✅ Создан шаблон файла: {csv_file}")
    print("📝 Заполните файл своими данными:")
    print("   - video_url: ссылка на YouTube видео")
    print("   - description: описание практики (необязательно)")
    print("   - number_practices: номер практики в программе (1-28 для 4 недель)")
    print("\n💡 Номера практик:")
    print("   - 1-7: первая неделя")
    print("   - 8-14: вторая неделя")
    print("   - 15-21: третья неделя")
    print("   - 22-28: четвертая неделя")


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
            description = row.get('description', '').strip()
            number_practices_str = row.get('number_practices', '').strip()
            
            # Проверяем обязательные поля
            if not video_url:
                print(f"❌ Строка {row_num}: пропущена (нет ссылки)")
                error_count += 1
                continue
            
            if not number_practices_str:
                print(f"❌ Строка {row_num}: пропущена (нет номера практики)")
                error_count += 1
                continue
            
            # Проверяем YouTube ссылку
            video_id = extract_video_id(video_url)
            if not video_id:
                print(f"❌ Строка {row_num}: неверная ссылка на YouTube")
                error_count += 1
                continue
            
            # Обрабатываем номер практики
            try:
                number_practices = int(number_practices_str)
                if number_practices < 1 or number_practices > 28:
                    print(f"❌ Строка {row_num}: номер практики должен быть от 1 до 28")
                    error_count += 1
                    continue
            except ValueError:
                print(f"❌ Строка {row_num}: неверный формат номера практики")
                error_count += 1
                continue
            
            # Получаем данные с YouTube
            print(f"📡 Получаем данные с YouTube...")
            youtube_data = get_youtube_data(video_url)
            if not youtube_data:
                print(f"❌ Строка {row_num}: не удалось получить данные с YouTube")
                error_count += 1
                continue
            
            # Показываем данные
            print(f"   Название: {youtube_data['title']}")
            print(f"   Канал: {youtube_data['channel_name']}")
            print(f"   Длительность: {youtube_data['duration_minutes']} минут")
            if description:
                print(f"   Описание: {description}")
            print(f"   Номер практики: {number_practices}")
            
            # Добавляем в базу данных
            success = add_newbie_practice(
                title=youtube_data['title'],
                video_url=video_url,
                duration_minutes=youtube_data['duration_minutes'],
                channel_name=youtube_data['channel_name'],
                description=description if description else youtube_data['description'],
                number_practices=number_practices
            )
            
            if success:
                print(f"✅ Строка {row_num}: успешно добавлена")
                added_count += 1
            else:
                print(f"❌ Строка {row_num}: ошибка добавления (возможно, дубликат)")
                error_count += 1
    
    # Итоговая статистика
    print("\n" + "=" * 50)
    print("📊 Результаты обработки:")
    print(f"✅ Успешно добавлено: {added_count}")
    print(f"❌ Ошибок: {error_count}")
    print(f"📈 Всего практик новичков в базе: {get_newbie_practice_count()}")


def show_statistics():
    """Показывает статистику по практикам новичков."""
    total_count = get_newbie_practice_count()
    max_number = get_max_newbie_practice_number()
    
    print(f"\n📊 Статистика практик новичков:")
    print(f"   Всего практик: {total_count}")
    print(f"   Максимальный номер практики: {max_number}")
    
    if max_number > 0:
        weeks = (max_number + 6) // 7  # Округляем вверх
        print(f"   Количество недель: {weeks}")
        
        # Показываем распределение по неделям
        print("\n📅 Распределение по неделям:")
        for week in range(1, weeks + 1):
            start_practice = (week - 1) * 7 + 1
            end_practice = min(week * 7, max_number)
            print(f"   Неделя {week}: практики {start_practice}-{end_practice}")


def main():
    """Главная функция."""
    print("🧘‍♀️ Массовое добавление йога практик для новичков")
    print("=" * 50)
    
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
            csv_file = input("📁 Введите имя CSV файла (по умолчанию newbie_practices.csv): ").strip()
            if not csv_file:
                csv_file = os.path.join(os.path.dirname(__file__), 'newbie_practices.csv')
            process_csv_file(csv_file)
        elif choice == '3':
            show_statistics()
        elif choice == '4':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")


if __name__ == "__main__":
    main()

