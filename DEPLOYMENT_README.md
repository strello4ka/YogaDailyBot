# 🚀 Деплой YogaDailyBot в Kubernetes

Этот документ описывает процесс развертывания YogaDailyBot в Kubernetes кластере.

## 📋 Предварительные требования

1. **Kubernetes кластер** (локальный или облачный)
2. **kubectl** - утилита командной строки для Kubernetes
3. **Docker** - для сборки образа
4. **Токен Telegram бота** - полученный от @BotFather

## 🏗️ Структура файлов

```
k8s/
├── configmap.yaml      # Конфигурация приложения
├── secret.yaml         # Секретные данные (токен бота)
├── pvc.yaml           # Persistent Volume Claim для БД
├── deployment.yaml    # Основной deployment
└── service.yaml       # Service для доступа
```

## 🚀 Быстрый деплой

### Автоматический деплой (рекомендуется)

```bash
# Делаем скрипт исполняемым
chmod +x deploy.sh

# Запускаем деплой
./deploy.sh
```

Скрипт автоматически:
- Соберет Docker образ
- Запросит токен бота
- Создаст все необходимые ресурсы в Kubernetes
- Покажет статус деплоя

### Ручной деплой

1. **Сборка образа:**
```bash
docker build -t yogadaily-bot:latest .
```

2. **Подготовка секрета:**
```bash
# Кодируем токен в base64
echo -n "your_bot_token_here" | base64

# Редактируем k8s/secret.yaml и вставляем закодированный токен
```

3. **Применение манифестов:**
```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

## 🔧 Конфигурация

### Переменные окружения

| Переменная | Описание | Источник |
|------------|----------|----------|
| `BOT_TOKEN` | Токен Telegram бота | Secret |
| `DEFAULT_TZ` | Часовой пояс | ConfigMap |
| `DB_PATH` | Путь к файлу БД | ConfigMap |
| `LOG_LEVEL` | Уровень логирования | ConfigMap |

### Ресурсы

- **CPU**: 100m (запрос) / 200m (лимит)
- **Memory**: 128Mi (запрос) / 256Mi (лимит)
- **Storage**: 1Gi (Persistent Volume)

## 📊 Мониторинг

### Просмотр статуса

```bash
# Статус подов
kubectl get pods -l app=yogadaily-bot

# Детальная информация о поде
kubectl describe pod -l app=yogadaily-bot

# Логи бота
kubectl logs -l app=yogadaily-bot -f
```

### Health Checks

Бот настроен с liveness и readiness пробами на порту 8080.

## 🔄 Обновление

### Обновление образа

```bash
# Собираем новый образ
docker build -t yogadaily-bot:latest .

# Перезапускаем deployment
kubectl rollout restart deployment/yogadaily-bot
```

### Обновление конфигурации

```bash
# Редактируем ConfigMap
kubectl edit configmap yogadaily-bot-config

# Перезапускаем поды для применения изменений
kubectl rollout restart deployment/yogadaily-bot
```

## 🛑 Удаление

```bash
# Удаляем все ресурсы
kubectl delete -f k8s/

# Или удаляем по отдельности
kubectl delete deployment yogadaily-bot
kubectl delete service yogadaily-bot-service
kubectl delete pvc yogadaily-bot-db-pvc
kubectl delete configmap yogadaily-bot-config
kubectl delete secret yogadaily-bot-secret
```

## 🔍 Troubleshooting

### Проблемы с запуском

1. **Проверьте логи:**
```bash
kubectl logs -l app=yogadaily-bot
```

2. **Проверьте статус подов:**
```bash
kubectl get pods -l app=yogadaily-bot
kubectl describe pod <pod-name>
```

3. **Проверьте события:**
```bash
kubectl get events --sort-by='.lastTimestamp'
```

### Частые проблемы

- **ImagePullBackOff**: Образ не найден. Убедитесь, что образ собран и доступен.
- **CrashLoopBackOff**: Ошибка в приложении. Проверьте логи и конфигурацию.
- **Pending**: Недостаточно ресурсов или проблемы с PVC.

## 🔐 Безопасность

- Токен бота хранится в Kubernetes Secret
- Приложение запускается под непривилегированным пользователем
- Используется минимальный набор системных зависимостей
- Health checks помогают обнаружить проблемы

## 📝 Примечания

- Бот использует SQLite базу данных, которая хранится в Persistent Volume
- Для продакшена рекомендуется использовать внешнюю БД (PostgreSQL, MySQL)
- При необходимости можно настроить горизонтальное масштабирование (HPA)
- Для мониторинга рекомендуется добавить Prometheus метрики
