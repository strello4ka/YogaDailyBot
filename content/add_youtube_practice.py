#!/usr/bin/env python3
"""
Скрипт для автоматического получения добавления одной йога практики в базу данных.
"""

import sys
import os
import re
from urllib.parse import urlparse, parse_qs

# Добавляем путь к модулю app в sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.db import add_yoga_practice, get_practice_count, weekday_to_name


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
                'time_practices': duration_minutes
            }
        
    except Exception as e:
        print(f"❌ Ошибка получения данных с YouTube: {e}")
        return None


def get_weekday_input():
    """Получает день недели от пользователя."""
    print("\n📅 Выберите день недели:")
    print("1. Понедельник")
    print("2. Вторник") 
    print("3. Среда")
    print("4. Четверг")
    print("5. Пятница")
    print("6. Суббота")
    print("7. Воскресенье")
    print("0. Любой день (не указывать)")
    
    while True:
        try:
            choice = input("\nВаш выбор (0-7): ").strip()
            if choice == '0':
                return None
            elif choice in ['1', '2', '3', '4', '5', '6', '7']:
                return int(choice)
            else:
                print("❌ Пожалуйста, введите число от 0 до 7!")
        except ValueError:
            print("❌ Пожалуйста, введите целое число!")


def add_practice_from_youtube():
    """Добавляет практику из YouTube ссылки."""
    
    print("🧘‍♀️ Добавление йога практики из YouTube")
    print("=" * 50)
    
    # Получаем ссылку от пользователя
    while True:
        video_url = input("🔗 Введите ссылку на YouTube видео: ").strip()
        
        if not video_url:
            print("❌ Ссылка не может быть пустой!")
            continue
            
        # Проверяем, что это YouTube ссылка
        video_id = extract_video_id(video_url)
        if not video_id:
            print("❌ Неверная ссылка на YouTube видео!")
            continue
            
        break
    
    print(f"\n📡 Получаем данные с YouTube...")
    
    # Получаем данные с YouTube
    youtube_data = get_youtube_data(video_url)
    if not youtube_data:
        print("❌ Не удалось получить данные с YouTube. Проверьте ссылку.")
        return
    
    # Показываем полученные данные
    print("\n📋 Данные с YouTube:")
    print(f"   Название: {youtube_data['title']}")
    print(f"   Канал: {youtube_data['channel_name']}")
    print(f"   Длительность: {youtube_data['time_practices']} минут")
    print(f"   Описание: {youtube_data['description'][:100]}...")
    
    # Получаем мое описание
    my_description = input("\n📝 Введите свое описание практики (необязательно): ").strip()
    if not my_description:
        my_description = None
    
    # Получаем день недели
    weekday = get_weekday_input()
    
    # Подтверждение
    print(f"\n📋 Проверьте данные:")
    print(f"   Название: {youtube_data['title']}")
    print(f"   Ссылка: {video_url}")
    print(f"   Длительность: {youtube_data['time_practices']} минут")
    print(f"   Канал: {youtube_data['channel_name']}")
    if my_description:
        print(f"   Мое описание: {my_description}")
    if weekday:
        print(f"   День недели: {weekday_to_name(weekday)}")
    else:
        print(f"   День недели: Любой день")
    
    confirm = input("\n✅ Добавить практику? (y/n): ").lower().strip()
    if confirm in ['y', 'yes', 'да', 'д']:
        success = add_yoga_practice(
            title=youtube_data['title'],
            video_url=video_url,
            time_practices=youtube_data['time_practices'],
            channel_name=youtube_data['channel_name'],
            description=youtube_data['description'],
            my_description=my_description,
            weekday=weekday
        )
        
        if success:
            print("🎉 Практика успешно добавлена!")
        else:
            print("❌ Ошибка при добавлении практики. Возможно, видео с таким URL уже существует.")
    else:
        print("❌ Добавление отменено.")


def show_statistics():
    """Показывает статистику базы данных."""
    print("\n📊 Статистика базы данных:")
    print("=" * 30)
    
    count = get_practice_count()
    print(f"   Всего практик: {count}")


def main():
    """Главная функция."""
    print("🧘‍♀️ Менеджер йога практик с YouTube")
    print("=" * 40)
    
    while True:
        print("\nВыберите действие:")
        print("1. 📝 Добавить практику из YouTube")
        print("2. 📊 Показать статистику")
        print("3. 🚪 Выйти")
        
        choice = input("\nВаш выбор (1-3): ").strip()
        
        if choice == '1':
            add_practice_from_youtube()
        elif choice == '2':
            show_statistics()
        elif choice == '3':
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")


if __name__ == "__main__":
    main()
