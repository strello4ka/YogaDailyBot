#!/bin/bash

# Скрипт для деплоя YogaDailyBot в Kubernetes
set -e

echo "🚀 Начинаем деплой YogaDailyBot в Kubernetes..."

# Проверяем наличие kubectl
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl не найден. Установите kubectl и попробуйте снова."
    exit 1
fi

# Проверяем подключение к кластеру
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Не удается подключиться к Kubernetes кластеру."
    echo "Убедитесь, что kubectl настроен правильно."
    exit 1
fi

# Проверяем наличие Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не найден. Установите Docker и попробуйте снова."
    exit 1
fi

echo "📦 Собираем Docker образ..."
docker build -t yogadaily-bot:latest .

echo "🔐 Создаем Secret с токеном бота..."
echo "Введите токен вашего Telegram бота:"
read -s BOT_TOKEN

# Кодируем токен в base64
BOT_TOKEN_B64=$(echo -n "$BOT_TOKEN" | base64)

# Создаем временный файл с секретом
cat > k8s/secret-temp.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: yogadaily-bot-secret
  labels:
    app: yogadaily-bot
type: Opaque
data:
  BOT_TOKEN: $BOT_TOKEN_B64
EOF

echo "📋 Применяем Kubernetes манифесты..."

# Создаем namespace если его нет
kubectl create namespace yogadaily-bot --dry-run=client -o yaml | kubectl apply -f -

# Применяем манифесты
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret-temp.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Удаляем временный файл с секретом
rm k8s/secret-temp.yaml

echo "⏳ Ждем запуска пода..."
kubectl wait --for=condition=ready pod -l app=yogadaily-bot --timeout=300s

echo "✅ Деплой завершен!"
echo ""
echo "📊 Статус деплоя:"
kubectl get pods -l app=yogadaily-bot
echo ""
echo "📝 Логи бота:"
kubectl logs -l app=yogadaily-bot --tail=20
echo ""
echo "🔍 Для просмотра логов используйте:"
echo "kubectl logs -l app=yogadaily-bot -f"
echo ""
echo "🛑 Для остановки бота используйте:"
echo "kubectl delete -f k8s/"
