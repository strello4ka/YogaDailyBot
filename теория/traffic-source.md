# Метки источников (аналог UTM)

Отслеживание, **откуда пришёл пользователь** при первом входе в бота.

## Как это работает

1. В посте / био / описании публикуете ссылку с меткой:
   `https://t.me/ИМЯ_БОТА?start=метка`
2. Человек нажимает Start.
3. Бот один раз сохраняет метку в `users.traffic_source` (первый вход).
4. Повторный `/start` или сброс онбординга метку **не меняют**.

Метка есть **только** если человек перешёл по ссылке с `?start=...`.  
Поиск бота по названию, `@username` без параметра или ссылка без `?start=` → `traffic_source` пустой (источник неизвестен).

## Правила имени метки

- Латиница, цифры, `_` или `-`
- Длина до 64 символов
- Рекомендуемый шаблон: `{канал}_{место}` или `{канал}_{место}_{кампания}`

Примеры ссылок (подставьте username бота):

| Место | Метка | Ссылка |
|-------|--------|--------|
| YouTube описание | `youtube_desc` | `https://t.me/Bot?start=youtube_desc` |
| YouTube Shorts | `youtube_shorts` | `https://t.me/Bot?start=youtube_shorts` |
| Instagram био | `ig_bio` | `https://t.me/Bot?start=ig_bio` |
| Instagram сторис | `ig_story` | `https://t.me/Bot?start=ig_story` |
| Instagram Reels | `ig_reels` | `https://t.me/Bot?start=ig_reels` |
| Telegram канал | `tg_channel` | `https://t.me/Bot?start=tg_channel` |

## Поля в БД

| Поле | Смысл |
|------|--------|
| `users.traffic_source` | Метка из ссылки (или NULL) |

Дата первого входа — в обычном поле `users.created_at`.

## SQL для DBeaver

Сколько пользователей по каждой метке:

```sql
SELECT
    COALESCE(traffic_source, '(без метки)') AS source,
    COUNT(*) AS users_count
FROM users
GROUP BY traffic_source
ORDER BY users_count DESC;
```

Новые за период с разбивкой по источнику:

```sql
SELECT
    COALESCE(traffic_source, '(без метки)') AS source,
    COUNT(*) AS users_count
FROM users
WHERE created_at >= '2026-07-01'
  AND created_at < '2026-08-01'
GROUP BY traffic_source
ORDER BY users_count DESC;
```

Доля без метки:

```sql
SELECT
    COUNT(*) FILTER (WHERE traffic_source IS NULL) AS without_source,
    COUNT(*) FILTER (WHERE traffic_source IS NOT NULL) AS with_source,
    COUNT(*) AS total
FROM users;
```
