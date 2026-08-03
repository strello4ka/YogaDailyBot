#!/usr/bin/env python3
"""Массовое добавление mood-практик из CSV (таблица mood_practices)."""

import csv
import os
import sys
import time
from urllib.parse import parse_qs, urlparse

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from app.config import get_db_connection_label
from data.db import add_mood_practice, get_mood_practice_count


def extract_video_id(url: str):
    parsed_url = urlparse(url)
    if parsed_url.hostname in ("www.youtube.com", "youtube.com"):
        if parsed_url.path == "/watch":
            return parse_qs(parsed_url.query).get("v", [None])[0]
        if parsed_url.path.startswith("/embed/"):
            return parsed_url.path.split("/")[2]
    elif parsed_url.hostname == "youtu.be":
        return parsed_url.path[1:]
    return None


def get_youtube_data(url: str, delay_seconds: int = 0):
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    try:
        import yt_dlp

        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": False}
        cookies_file = os.environ.get("YOUTUBE_COOKIES_FILE", "").strip()
        cookies_browser = os.environ.get("YOUTUBE_COOKIES_BROWSER", "").strip()
        if cookies_file and os.path.isfile(cookies_file):
            ydl_opts["cookiefile"] = cookies_file
        elif cookies_browser:
            ydl_opts["cookiesfrombrowser"] = (cookies_browser,)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration_seconds = info.get("duration", 0) or 0
        return {
            "title": info.get("title", "Без названия"),
            "channel_name": info.get("uploader", "Неизвестный канал"),
            "description": (info.get("description") or "")[:1000],
            "time_practices": duration_seconds // 60,
        }
    except Exception as e:
        print(f"❌ Ошибка получения данных с YouTube: {e}")
        err = str(e).lower()
        if "not a bot" in err or "sign in to confirm" in err:
            print(
                "💡 Добавьте в .env: YOUTUBE_COOKIES_BROWSER=chrome\n"
                "   (или export YOUTUBE_COOKIES_BROWSER=chrome в терминале)"
            )
        return None


def parse_without_mat(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "да", "y"}


def create_csv_template():
    csv_file = os.path.join(os.path.dirname(__file__), "mood_practices.csv")
    with open(csv_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["video_url", "my_description", "difficulty", "without_mat"])
        writer.writerow(
            [
                "https://www.youtube.com/watch?v=example_lazy",
                "Очень мягкая практика для ленивого дня",
                "сверх низкая",
                "",
            ]
        )
        writer.writerow(
            [
                "https://www.youtube.com/watch?v=example_five",
                "Короткая зарядка до 8 минут",
                "низкая",
                "",
            ]
        )
        writer.writerow(
            [
                "https://www.youtube.com/watch?v=example_no_mat",
                "Можно без коврика",
                "средняя",
                "true",
            ]
        )

    print(f"✅ Создан шаблон файла: {csv_file}")
    print("📝 Заполните файл своими данными:")
    print("   - video_url: ссылка на YouTube")
    print("   - my_description: ваше описание (необязательно)")
    print("   - difficulty: для «Ленивые дни» — сверх низкая, для «Хард» — сверх высокая")
    print("   - without_mat: true — для фильтра «Без коврика»")
    print("   - для «Мини» важна длительность видео (подтянется с YouTube, до 8 мин)")


def process_csv_file(csv_file: str):
    if not os.path.exists(csv_file):
        print(f"❌ Файл {csv_file} не найден!")
        return

    print(f"📁 Обрабатываем файл: {csv_file}")
    print("=" * 50)

    added_count = 0
    error_count = 0

    with open(csv_file, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row_num, row in enumerate(reader, 1):
            print(f"\n📝 Обрабатываем строку {row_num}...")

            video_url = (row.get("video_url") or "").strip()
            my_description = (row.get("my_description") or "").strip()
            difficulty = (row.get("difficulty") or "").strip() or None
            without_mat = parse_without_mat(row.get("without_mat") or "")

            if not video_url:
                print(f"❌ Строка {row_num}: пропущена (нет ссылки)")
                error_count += 1
                continue

            if not extract_video_id(video_url):
                print(f"❌ Строка {row_num}: неверная ссылка на YouTube")
                error_count += 1
                continue

            print("📡 Получаем данные с YouTube...")
            youtube_data = get_youtube_data(video_url, delay_seconds=2 if row_num > 1 else 0)
            if not youtube_data:
                print(f"❌ Строка {row_num}: не удалось получить данные с YouTube")
                error_count += 1
                continue

            print(f"   Название: {youtube_data['title']}")
            print(f"   Канал: {youtube_data['channel_name']}")
            print(f"   Длительность: {youtube_data['time_practices']} минут")
            if my_description:
                print(f"   Моё описание: {my_description}")
            if difficulty:
                print(f"   Сложность: {difficulty}")
            if without_mat:
                print("   Без коврика: да")

            success, message = add_mood_practice(
                title=youtube_data["title"],
                video_url=video_url,
                time_practices=youtube_data["time_practices"],
                channel_name=youtube_data["channel_name"],
                description=youtube_data["description"],
                my_description=my_description or None,
                difficulty=difficulty,
                without_mat=without_mat,
            )

            if success:
                print(f"✅ Строка {row_num}: {message}")
                added_count += 1
            else:
                print(f"❌ Строка {row_num}: {message}")
                error_count += 1

    print("\n" + "=" * 50)
    print("📊 Результаты обработки:")
    print(f"✅ Успешно добавлено: {added_count}")
    print(f"❌ Ошибок: {error_count}")
    print(f"📈 Всего mood-практик в базе: {get_mood_practice_count()}")


def main():
    print("🧘‍♀️ Массовое добавление mood-практик (By mood)")
    print("=" * 40)
    db_label = get_db_connection_label()
    print(f"📡 База данных (из .env): {db_label}")
    if not os.environ.get("YOUTUBE_COOKIES_BROWSER", "").strip():
        print("⚠️  В .env нет YOUTUBE_COOKIES_BROWSER=chrome — YouTube может блокировать запросы.")

    while True:
        print("\nВыберите действие:")
        print("1. 📝 Создать шаблон CSV файла")
        print("2. 📁 Обработать CSV файл")
        print("3. 📊 Показать статистику")
        print("4. 🚪 Выйти")

        choice = input("\nВаш выбор (1-4): ").strip()

        if choice == "1":
            create_csv_template()
        elif choice == "2":
            csv_file = input(
                "📁 Введите имя CSV файла (по умолчанию mood_practices.csv): "
            ).strip()
            if not csv_file:
                csv_file = os.path.join(os.path.dirname(__file__), "mood_practices.csv")
            process_csv_file(csv_file)
        elif choice == "3":
            count = get_mood_practice_count()
            print(f"\n📊 Всего mood-практик в базе: {count}")
        elif choice == "4":
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")


if __name__ == "__main__":
    main()
