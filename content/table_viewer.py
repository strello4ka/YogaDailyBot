#!/usr/bin/env python3
"""
Скрипт для отображения настоящей таблицы БД со всеми полями
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.db import get_all_yoga_practices, weekday_to_name

def main():
    print("📊 ТАБЛИЦА БАЗЫ ДАННЫХ ЙОГА ПРАКТИК")
    print("=" * 200)
    
    # Получаем все практики
    practices = get_all_yoga_practices()
    
    if not practices:
        print("❌ В базе данных нет практик")
        return
    
    # Заголовок таблицы
    print(f"{'ID':<4} | {'День':<12} | {'Длит.':<6} | {'Название':<60} | {'Канал':<30} | {'Моё описание':<50} | {'Ссылка':<50}")
    print("-" * 200)
    
    # Выводим каждую практику
    for practice in practices:
        # Распаковываем кортеж
        practices_id, title, video_url, time_practices, channel_name, description, my_description, weekday, created_at, updated_at = practice
        
        # Получаем название дня недели
        weekday_name = weekday_to_name(weekday) if weekday else "Любой"
        
        # Обрезаем длинные строки для таблицы
        title_short = title[:57] + "..." if len(title) > 60 else title
        channel_short = channel_name[:27] + "..." if len(channel_name) > 30 else channel_name
        my_desc_short = my_description[:47] + "..." if my_description and len(my_description) > 50 else (my_description or "—")
        url_short = video_url[:47] + "..." if len(video_url) > 50 else video_url
        
        # Выводим строку таблицы
        print(f"{practices_id:<4} | {weekday_name:<12} | {time_practices:<6} | {title_short:<60} | {channel_short:<30} | {my_desc_short:<50} | {url_short:<50}")
    
    print("-" * 200)
    print(f"Всего практик: {len(practices)}")
    
    # Дополнительная информация
    print("\n📋 ПОЛНАЯ СТРУКТУРА ТАБЛИЦЫ:")
    print("=" * 50)
    print("Поля в базе данных:")
    print("• practices_id - ID практики")
    print("• title - Название видео")
    print("• video_url - Ссылка на YouTube")
    print("• time_practices - Длительность в минутах")
    print("• channel_name - Название канала")
    print("• description - Описание с YouTube")
    print("• my_description - Моё описание (заполняется вручную)")
    print("• weekday - День недели (1-7, NULL для любого дня)")
    print("• created_at - Дата создания записи")
    print("• updated_at - Дата последнего обновления")

if __name__ == "__main__":
    main()
