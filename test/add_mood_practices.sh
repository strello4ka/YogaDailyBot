#!/bin/bash
# Добавление mood-практик из app/content/mood_practices.csv в тестовую БД.
# Использование: ./test/add_mood_practices.sh (из корня проекта, venv активирован)

cd "$(dirname "$0")/.."
export ENV_FILE=test/.env.test
python app/content/add_mood_practices.py
