#!/bin/bash
# Добавление бонусных практик из app/content/bonus_practices.csv в тестовую БД.
# Использование: ./test/add_bonus_practices.sh (из корня проекта, venv активирован)
# Данные берутся из тех же CSV, что и для прода; пишется только в тестовую БД.

cd "$(dirname "$0")/.."
export ENV_FILE=test/.env.test
python app/content/add_bonus_practices.py
