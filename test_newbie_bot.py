#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой логики новичков в боте.
"""

import sys
import os
import asyncio
from unittest.mock import Mock

# Добавляем путь к корневой папке проекта в sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data.db import (
    init_database,
    save_user_time,
    get_user_time,
    add_newbie_practice,
    get_newbie_practice_by_number,
    get_current_weekday,
    increment_user_days
)
from app.schedule.scheduler import send_newbie_practice, send_practice_to_user


class MockContext:
    """Мок-объект для контекста бота."""
    def __init__(self):
        self.bot = Mock()
        self.bot.send_message = Mock()


async def test_newbie_practice_sending():
    """Тестирует отправку практики новичку."""
    print("🧪 Тестируем отправку практики новичку...")
    
    try:
        # Инициализируем базу данных
        init_database()
        print("✅ База данных инициализирована")
        
        # Добавляем тестовую практику для новичков
        practice_data = {
            'title': 'Тестовая практика для новичков',
            'video_url': 'https://www.youtube.com/watch?v=test_newbie',
            'duration_minutes': 15,
            'channel_name': 'Test Channel',
            'description': 'Простая практика для начинающих',
            'number_practices': 1
        }
        
        success = add_newbie_practice(**practice_data)
        if success:
            print("✅ Тестовая практика добавлена")
        else:
            print("❌ Ошибка добавления тестовой практики")
            return False
        
        # Создаем тестового пользователя
        test_user_id = 123456789
        test_chat_id = 123456789
        current_weekday = get_current_weekday()
        
        # Сохраняем пользователя как новичка
        save_user_time(
            user_id=test_user_id,
            chat_id=test_chat_id,
            notify_time="09:00",
            user_name="Test Newbie User",
            onboarding_weekday=current_weekday
        )
        print(f"✅ Тестовый пользователь создан с днем регистрации: {current_weekday}")
        
        # Получаем данные пользователя
        user_data = get_user_time(test_user_id)
        if user_data:
            chat_id, notify_time, user_name, user_phone, user_days, onboarding_weekday = user_data
            print(f"✅ Данные пользователя:")
            print(f"   - Дни: {user_days}")
            print(f"   - День регистрации: {onboarding_weekday}")
        
        # Тестируем отправку практики новичку
        mock_context = MockContext()
        
        # Проверяем, что пользователь считается новичком (user_days <= 28)
        if user_days <= 28:
            print("✅ Пользователь определен как новичок")
            
            # Тестируем функцию send_newbie_practice
            await send_newbie_practice(
                context=mock_context,
                user_id=test_user_id,
                chat_id=test_chat_id,
                onboarding_weekday=onboarding_weekday,
                day_number=user_days + 1
            )
            print("✅ Практика для новичка отправлена успешно")
            
            # Проверяем, что сообщение было отправлено
            if mock_context.bot.send_message.called:
                print("✅ Сообщение отправлено через бота")
                call_args = mock_context.bot.send_message.call_args
                print(f"   - Chat ID: {call_args[1]['chat_id']}")
                print(f"   - Текст содержит 'день': {'день' in call_args[1]['text']}")
            else:
                print("❌ Сообщение не было отправлено")
                return False
        else:
            print("❌ Пользователь не определен как новичок")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_practice_number_calculation():
    """Тестирует вычисление номера практики."""
    print("\n🧪 Тестируем вычисление номера практики...")
    
    try:
        # Тестируем различные сценарии дня регистрации
        test_scenarios = [
            (7, 1),   # Воскресенье → Практика #1
            (1, 2),   # Понедельник → Практика #2
            (2, 3),   # Вторник → Практика #3
            (3, 4),   # Среда → Практика #4
            (4, 5),   # Четверг → Практика #5
            (5, 6),   # Пятница → Практика #6
            (6, 7),   # Суббота → Практика #7
        ]
        
        for onboarding_weekday, expected_practice in test_scenarios:
            # Вычисляем номер практики: (onboarding_weekday % 7) + 1
            calculated_practice = (onboarding_weekday % 7) + 1
            
            weekday_names = {1: "Понедельник", 2: "Вторник", 3: "Среда", 4: "Четверг", 
                           5: "Пятница", 6: "Суббота", 7: "Воскресенье"}
            
            weekday_name = weekday_names.get(onboarding_weekday, f"День {onboarding_weekday}")
            
            print(f"   {weekday_name} ({onboarding_weekday}) → Практика #{calculated_practice} (ожидалось #{expected_practice})")
            
            if calculated_practice == expected_practice:
                print(f"   ✅ Правильно")
            else:
                print(f"   ❌ Неправильно")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования вычисления: {e}")
        return False


async def main():
    """Главная функция тестирования."""
    print("🧘‍♀️ Тестирование новой логики новичков в боте")
    print("=" * 60)
    
    tests = [
        test_newbie_practice_sending,
        test_practice_number_calculation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if await test():
            passed += 1
        print()
    
    print("=" * 60)
    print(f"📊 Результаты тестирования: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены успешно!")
        print("\n💡 Теперь вы можете протестировать бота в Telegram:")
        print("   1. Найдите вашего бота в Telegram")
        print("   2. Отправьте команду /start")
        print("   3. Выберите время для уведомлений")
        print("   4. Отправьте команду /test для получения тестовой практики")
        return True
    else:
        print("❌ Некоторые тесты не прошли")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
