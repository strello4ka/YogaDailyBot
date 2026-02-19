#!/bin/bash
# Добавление практик из app/content/yoga_practices.csv в тестовую БД.
# Использование: ./test/add_practices.sh (из корня проекта, venv активирован)
# Данные берутся из тех же CSV, что и для прода; пишется только в тестовую БД.

cd "$(dirname "$0")/.."
export ENV_FILE=test/.env.test
python app/content/add_practices.py
