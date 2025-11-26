#!/usr/bin/env python3
"""
Скрипт для добавления одной бонусной практики по ссылке на YouTube.
"""

import sys
import os
from urllib.parse import urlparse, parse_qs

# Настраиваем sys.path, чтобы можно было импортировать data.db
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from data.db import (  # noqa: E402 - импортируем после модификации sys.path
    add_bonus_practice,
    get_bonus_practice_count,
    get_yoga_practice_by_id
)


def extract_video_id(url: str):
    """Проверяем ссылку на YouTube до того, как идти за данными."""
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
    """Подтягиваем всё необходимое о видео, чтобы не вводить руками."""
    try:
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        return {
            'title': info.get('title', 'Без названия'),
            'channel_name': info.get('uploader', 'Неизвестный канал'),
            'description': info.get('description', '')[:1000],
            'time_practices': (info.get('duration', 0) or 0) // 60
        }
    except Exception as exc:
        print(f"❌ Ошибка получения данных с YouTube: {exc}")
        return None


def ask_parent_practice_id():
    """Запрашиваем ID основной практики и проверяем, что она есть в БД."""
    while True:
        practice_id_str = input("🔢 Введи ID основной практики: ").strip()
        if not practice_id_str:
            print("❌ ID не может быть пустым")
            continue

        if not practice_id_str.isdigit():
            print("❌ ID должен быть числом")
            continue

        practice_id = int(practice_id_str)
        if not get_yoga_practice_by_id(practice_id):
            print(f"❌ Практика с ID {practice_id} не найдена. Проверь список и попробуй снова.")
            continue

        return practice_id


def add_bonus_from_youtube():
    """Основной сценарий: спросить данные и добавить бонус."""
    print("💫 Добавление бонусной практики")
    print("=" * 40)

    parent_practice_id = ask_parent_practice_id()

    while True:
        video_url = input("🔗 Введи ссылку на YouTube видео: ").strip()
        if not video_url:
            print("❌ Ссылка не может быть пустой")
            continue

        if not extract_video_id(video_url):
            print("❌ Ссылка должна вести на YouTube")
            continue

        break

    print("\n📡 Получаем данные о бонусе...")
    youtube_data = get_youtube_data(video_url)
    if not youtube_data:
        print("❌ Не удалось получить данные. Проверь ссылку.")
        return

    print("\n📋 Данные о бонусе:")
    print(f"   Название: {youtube_data['title']}")
    print(f"   Канал: {youtube_data['channel_name']}")
    print(f"   Длительность: {youtube_data['time_practices']} минут")

    my_description = input("\n📝 Твой текст для бонуса (опционально): ").strip() or None
    intensity = input("🔥 Интенсивность бонуса (опционально): ").strip() or None

    confirm = input("\n✅ Добавляем бонус? (y/n): ").strip().lower()
    if confirm not in ('y', 'yes', 'д', 'да'):
        print("🚫 Добавление отменено.")
        return

    success = add_bonus_practice(
        parent_practice_id=parent_practice_id,
        title=youtube_data['title'],
        video_url=video_url,
        time_practices=youtube_data['time_practices'],
        channel_name=youtube_data['channel_name'],
        description=youtube_data['description'],
        my_description=my_description,
        intensity=intensity
    )

    if success:
        print("🎉 Бонусная практика сохранена.")
        print(f"📈 Теперь бонусов в базе: {get_bonus_practice_count()}")
    else:
        print("❌ Не удалось сохранить бонус. Посмотри лог для деталей.")


def main():
    """Простое меню, если захочется добавить несколько бонусов подряд."""
    while True:
        print("\nВыберите действие:")
        print("1. ➕ Добавить бонусную практику")
        print("2. 📊 Показать количество бонусов")
        print("3. 🚪 Выйти")

        choice = input("\nВаш выбор (1-3): ").strip()

        if choice == '1':
            add_bonus_from_youtube()
        elif choice == '2':
            print(f"\n📊 В базе бонусных практик: {get_bonus_practice_count()}")
        elif choice == '3':
            print("👋 До встречи!")
            break
        else:
            print("❌ Неверный выбор. Попробуй снова.")


if __name__ == "__main__":
    main()

