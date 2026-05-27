#!/bin/bash
# Запуск тестового бота с конфигом test/.env.test
# Использование: ./test/run_test.sh (из корня проекта, с активированным venv при необходимости)

cd "$(dirname "$0")/.."
export ENV_FILE=test/.env.test

# Предпочитаем Python из локального venv, чтобы избежать запуска на системном 3.9.
if [ -x "./venv/bin/python" ]; then
  PYTHON_BIN="./venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Ошибка: не найден Python интерпретатор."
  exit 1
fi

# Проверка минимальной версии: проект запускаем минимум на Python 3.9.
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "Ошибка: нужен Python 3.9+ (текущий: $("$PYTHON_BIN" -V 2>&1))."
  echo "Подсказка: активируйте venv или установите Python 3.9+."
  exit 1
}

"$PYTHON_BIN" -m app.main
