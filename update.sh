#!/bin/bash

# Скрипт для обновления YogaDailyBot в Kubernetes
set -e

echo "🔄 Начинаем обновление YogaDailyBot..."

# Проверяем наличие kubectl
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl не найден. Установите kubectl и попробуйте снова."
    exit 1
fi

# Проверяем подключение к кластеру
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Не удается подключиться к Kubernetes кластеру."
    exit 1
fi

# Проверяем наличие Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не найден. Установите Docker и попробуйте снова."
    exit 1
fi

echo "📦 Собираем новый Docker образ..."
docker build -t yogadaily-bot:latest .

echo "🚀 Обновляем deployment в Kubernetes..."
kubectl rollout restart deployment/yogadaily-bot

echo "⏳ Ждем завершения обновления..."
kubectl rollout status deployment/yogadaily-bot --timeout=300s

echo "✅ Обновление завершено!"
echo ""
echo "📊 Статус подов:"
kubectl get pods -l app=yogadaily-bot
echo ""
echo "📝 Последние логи:"
kubectl logs -l app=yogadaily-bot --tail=10
echo ""
echo "🔍 Для просмотра логов в реальном времени:"
echo "kubectl logs -l app=yogadaily-bot -f"
