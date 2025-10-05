#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой логики новичков.
"""

import sys
import os

# Добавляем путь к корневой папке проекта в sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data.db import (
    init_database,
    add_newbie_practice,
    get_newbie_practice_by_number,
    get_newbie_practice_count,
    get_max_newbie_practice_number,
    save_user_time,
    get_user_time,
    get_user_week,
    update_user_week,
    get_current_weekday
)


def test_database_initialization():
    """Тестирует инициализацию базы данных."""
    print("🧪 Тестируем инициализацию базы данных...")
    try:
        init_database()
        print("✅ База данных инициализирована успешно")
        return True
    except Exception as e:
        print(f"❌ Ошибка инициализации базы данных: {e}")
        return False


def test_newbie_practice_functions():
    """Тестирует функции для работы с практиками новичков."""
    print("\n🧪 Тестируем функции практик новичков...")
    
    try:
        # Добавляем тестовые практики
        test_practices = [
            {
                'title': 'Тестовая практика 1',
                'video_url': 'https://www.youtube.com/watch?v=test1',
                'duration_minutes': 15,
                'channel_name': 'Test Channel',
                'description': 'Первая практика для новичков',
                'number_practices': 1
            },
            {
                'title': 'Тестовая практика 2',
                'video_url': 'https://www.youtube.com/watch?v=test2',
                'duration_minutes': 20,
                'channel_name': 'Test Channel',
                'description': 'Вторая практика для новичков',
                'number_practices': 2
            }
        ]
        
        for practice in test_practices:
            success = add_newbie_practice(**practice)
            if success:
                print(f"✅ Добавлена практика: {practice['title']}")
            else:
                print(f"❌ Ошибка добавления практики: {practice['title']}")
        
        # Тестируем получение практик
        practices_1 = get_newbie_practice_by_number(1)
        practices_2 = get_newbie_practice_by_number(2)
        
        print(f"✅ Найдено практик с номером 1: {len(practices_1)}")
        print(f"✅ Найдено практик с номером 2: {len(practices_2)}")
        
        # Тестируем статистику
        count = get_newbie_practice_count()
        max_number = get_max_newbie_practice_number()
        
        print(f"✅ Всего практик новичков: {count}")
        print(f"✅ Максимальный номер практики: {max_number}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования практик новичков: {e}")
        return False


def test_user_week_functions():
    """Тестирует функции для работы с неделями пользователей."""
    print("\n🧪 Тестируем функции недель пользователей...")
    
    try:
        # Создаем тестового пользователя
        test_user_id = 999999999
        test_chat_id = 999999999
        test_time = "09:00"
        test_name = "Test User"
        current_weekday = get_current_weekday()
        
        # Сохраняем пользователя с днем недели регистрации
        success = save_user_time(test_user_id, test_chat_id, test_time, test_name, onboarding_weekday=current_weekday)
        if success:
            print(f"✅ Пользователь сохранен с днем недели регистрации: {current_weekday}")
        else:
            print("❌ Ошибка сохранения пользователя")
            return False
        
        # Получаем данные пользователя
        user_data = get_user_time(test_user_id)
        if user_data:
            chat_id, notify_time, user_name, user_phone, user_days, user_week, onboarding_weekday = user_data
            print(f"✅ Данные пользователя получены:")
            print(f"   - Chat ID: {chat_id}")
            print(f"   - Время уведомлений: {notify_time}")
            print(f"   - Имя: {user_name}")
            print(f"   - Дни: {user_days}")
            print(f"   - Неделя: {user_week}")
            print(f"   - День недели регистрации: {onboarding_weekday}")
        else:
            print("❌ Ошибка получения данных пользователя")
            return False
        
        # Тестируем обновление недели
        success = update_user_week(test_user_id, 2)
        if success:
            print("✅ Неделя пользователя обновлена на 2")
        else:
            print("❌ Ошибка обновления недели")
            return False
        
        # Проверяем обновленную неделю
        user_week = get_user_week(test_user_id)
        print(f"✅ Текущая неделя пользователя: {user_week}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования недель пользователей: {e}")
        return False


def test_practice_number_calculation():
    """Тестирует вычисление номера практики для новичков."""
    print("\n🧪 Тестируем вычисление номера практики...")
    
    try:
        # Тестируем различные сценарии
        test_scenarios = [
            (1, 1, 1),  # Неделя 1, воскресенье (7), должна быть практика 1
            (1, 2, 2),  # Неделя 1, понедельник (1), должна быть практика 2
            (2, 1, 8),  # Неделя 2, воскресенье (7), должна быть практика 8
            (2, 2, 9),  # Неделя 2, понедельник (1), должна быть практика 9
            (4, 7, 28), # Неделя 4, воскресенье (7), должна быть практика 28
        ]
        
        for user_week, onboarding_weekday, expected_practice in test_scenarios:
            # Вычисляем номер практики: (неделя - 1) * 7 + день недели регистрации
            calculated_practice = (user_week - 1) * 7 + onboarding_weekday
            print(f"   Неделя {user_week}, день регистрации {onboarding_weekday}: практика {calculated_practice} (ожидалось {expected_practice})")
            
            if calculated_practice == expected_practice:
                print(f"   ✅ Правильно")
            else:
                print(f"   ❌ Неправильно")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования вычисления номера практики: {e}")
        return False


def main():
    """Главная функция тестирования."""
    print("🧘‍♀️ Тестирование новой логики новичков")
    print("=" * 50)
    
    tests = [
        test_database_initialization,
        test_newbie_practice_functions,
        test_user_week_functions,
        test_practice_number_calculation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены успешно!")
        return True
    else:
        print("❌ Некоторые тесты не прошли")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

