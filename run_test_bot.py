#!/usr/bin/env python3
"""
Скрипт для запуска тестового бота локально.
"""

import os
import sys
import subprocess

def run_test_bot():
    """Запускает тестового бота локально."""
    
    print("🤖 Запуск тестового бота...")
    
    # Проверяем наличие тестового токена
    test_token = os.getenv('TEST_BOT_TOKEN')
    if not test_token:
        print("❌ Не найден TEST_BOT_TOKEN в переменных окружения")
        print("💡 Установите: export TEST_BOT_TOKEN='ваш_тестовый_токен'")
        return False
    
    # Устанавливаем переменную окружения для тестового бота
    os.environ['BOT_TOKEN'] = test_token
    
    print(f"✅ Используется тестовый токен: {test_token[:10]}...")
    print("🚀 Запускаем бота...")
    print("💡 Найдите вашего тестового бота в Telegram и протестируйте!")
    
    try:
        # Запускаем бота
        subprocess.run([sys.executable, '-m', 'app.main'], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        return False
    
    return True

if __name__ == "__main__":
    run_test_bot()

