#!/usr/bin/env python3
"""
Скрипт для создания тестового пользователя-новичка.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data.db import init_database, save_user_time, get_current_weekday

def create_test_newbie_user(user_id, chat_id, user_name="Test Newbie"):
    """Создает тестового пользователя-новичка."""
    
    # Инициализируем базу данных
    init_database()
    
    # Получаем текущий день недели
    current_weekday = get_current_weekday()
    
    # Сохраняем пользователя как новичка
    success = save_user_time(
        user_id=user_id,
        chat_id=chat_id,
        notify_time="09:00",
        user_name=user_name,
        onboarding_weekday=current_weekday
    )
    
    if success:
        print(f"✅ Тестовый пользователь-новичок создан:")
        print(f"   - User ID: {user_id}")
        print(f"   - Chat ID: {chat_id}")
        print(f"   - Имя: {user_name}")
        print(f"   - День регистрации: {current_weekday}")
        print(f"   - Время уведомлений: 09:00")
        print(f"\n💡 Теперь отправьте команду /test в боте для проверки новой логики!")
        return True
    else:
        print(f"❌ Ошибка создания тестового пользователя")
        return False

if __name__ == "__main__":
    # Замените на ваши реальные ID из команды /myid
    user_id = int(input("Введите ваш User ID (из команды /myid): "))
    chat_id = int(input("Введите ваш Chat ID (из команды /myid): "))
    user_name = input("Введите ваше имя (или нажмите Enter для 'Test Newbie'): ") or "Test Newbie"
    
    create_test_newbie_user(user_id, chat_id, user_name)
