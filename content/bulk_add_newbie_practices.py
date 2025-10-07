#!/usr/bin/env python3
"""
Скрипт для массового добавления йога практик для новичков из CSV файла.
"""

import sys
import os
import csv
from urllib.parse import urlparse, parse_qs

# Добавляем путь к корневой папке проекта в sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from data.postgres_db import add_newbie_practice, get_newbie_practice_count, get_max_newbie_practice_number


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
            'ignoreerrors': True,  # Игнорируем ошибки формата
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
        
        # Заголовки (идентичны yoga_practices, но вместо weekday - number_practices)
        writer.writerow([
            'video_url',
            'my_description',
            'intensity',
            'number_practices'
        ])
        
        # Примеры строк
        writer.writerow([
            'https://www.youtube.com/watch?v=example1',
            'Первая практика для новичков - основы дыхания',
            'легкая',
            '1'
        ])
        writer.writerow([
            'https://www.youtube.com/watch?v=example2',
            'Вторая практика - простые асаны',
            'средняя',
            '1'
        ])
        writer.writerow([
            'https://www.youtube.com/watch?v=example3',
            'Третья практика - растяжка',
            'легкая',
            '2'
        ])
    
    print(f"✅ Создан шаблон файла: {csv_file}")
    print("📝 Заполните файл своими данными:")
    print("   - video_url: ссылка на YouTube видео (обязательно)")
    print("   - my_description: ваше описание практики (необязательно)")
    print("   - intensity: интенсивность - 'легкая', 'средняя' или 'высокая' (необязательно)")
    print("   - number_practices: номер практики (1-7, обязательно)")
    print("\n💡 Номера практик соответствуют дням недели:")
    print("   - 1: практика для тех, кто начал в воскресенье")
    print("   - 2: практика для тех, кто начал в понедельник")
    print("   - 3: практика для тех, кто начал во вторник")
    print("   - 4: практика для тех, кто начал в среду")
    print("   - 5: практика для тех, кто начал в четверг")
    print("   - 6: практика для тех, кто начал в пятницу")
    print("   - 7: практика для тех, кто начал в субботу")


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
            intensity = row.get('intensity', '').strip()
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
                if number_practices < 1 or number_practices > 7:
                    print(f"❌ Строка {row_num}: номер практики должен быть от 1 до 7")
                    error_count += 1
                    continue
            except ValueError:
                print(f"❌ Строка {row_num}: неверный формат номера практики")
                error_count += 1
                continue
            
            # Проверяем интенсивность
            valid_intensities = ['легкая', 'средняя', 'высокая', '']
            if intensity and intensity not in valid_intensities:
                print(f"⚠️ Строка {row_num}: неверная интенсивность '{intensity}', будет использовано пустое значение")
                intensity = None
            elif not intensity:
                intensity = None
            
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
            if youtube_data['description']:
                print(f"   Описание YouTube: {youtube_data['description'][:100]}...")
            if my_description:
                print(f"   Мое описание: {my_description}")
            if intensity:
                print(f"   Интенсивность: {intensity}")
            print(f"   Номер практики: {number_practices}")
            
            # Добавляем в базу данных
            success = add_newbie_practice(
                title=youtube_data['title'],
                video_url=video_url,
                time_practices=youtube_data['duration_minutes'],
                channel_name=youtube_data['channel_name'],
                description=youtube_data['description'],
                my_description=my_description if my_description else None,
                intensity=intensity,
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
        # Показываем распределение по номерам практик
        print("\n📅 Распределение по номерам:")
        from data.postgres_db import get_newbie_practice_by_number
        for num in range(1, min(max_number + 1, 8)):  # Максимум 7 номеров
            practices = get_newbie_practice_by_number(num)
            day_names = ['', 'воскресенье', 'понедельник', 'вторник', 'среду', 'четверг', 'пятницу', 'субботу']
            day_name = day_names[num] if num <= 7 else f'номер {num}'
            print(f"   Практика #{num} (для начавших в {day_name}): {len(practices)} практик(и)")


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

