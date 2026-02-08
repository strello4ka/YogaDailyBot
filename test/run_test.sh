#!/bin/bash
# Запуск тестового бота с конфигом test/.env.test
# Использование: ./test/run_test.sh (из корня проекта, с активированным venv при необходимости)

cd "$(dirname "$0")/.."
export ENV_FILE=test/.env.test
python -m app.main
