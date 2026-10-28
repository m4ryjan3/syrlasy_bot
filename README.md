# Syrlasy: Neon + Render + UptimeRobot

Бот работает через Telegram webhook на Render. В PostgreSQL Neon сохраняются
языки пользователей, связи обращений с админ-чатом и состояние диалогов (FSM).
Команды, тексты и кнопки сохранены. SQLite нужен только для переноса старых данных;
`bot.db` и `.env` не попадают в Docker-образ.

## 1. Создай базу в Neon

1. Зарегистрируйся на [neon.tech](https://neon.tech/) и создай проект PostgreSQL.
   Выбери регион рядом с Render, например Frankfurt. Проверь лимиты выбранного плана.
2. В **Connect** выбери базу и пользователя. Для одного экземпляра бота достаточно
   прямого подключения: отключи **Connection pooling**.
3. Сохрани URL подключения в менеджере паролей. Формат для этого бота:

   ```text
   postgresql://USER:PASSWORD@ep-YOUR-ENDPOINT.REGION.aws.neon.tech/neondb?sslmode=verify-full
   ```

   Используй свой host, database, user и password из Neon; не копируй пример буквально.
   `sslmode=verify-full` проверяет сертификат и имя сервера. Сохрани URL-экранирование
   спецсимволов пароля. Для asyncpg нужен URL без libpq-опций вроде `channel_binding`:
   этот драйвер их не поддерживает. Если политика твоей базы требует именно channel
   binding, текущий драйвер для такой политики не подходит — не отключай требование.
4. Полный URL содержит пароль: вводи его только в Render Environment или локальный
   `.env`, не в Git и не в чат.

Приложение само создаёт таблицы. Пул небольшой (до 3 соединений); неиспользуемые
соединения закрываются через 60 секунд. Prepared statement cache отключён для
совместимости с transaction pooler, если позже понадобится pooled endpoint.

## 2. Подготовь данные перед переключением

Если у старого бота есть данные:

1. Скачай актуальный `bot.db` со старого сервера и сделай резервную копию. Файл в
   репозитории может быть устаревшим.
2. Останови старого бота, чтобы новые изменения не потерялись во время переноса.
3. На компьютере из корня проекта:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   test -e .env || cp .env.example .env
   ```

4. В локальном `.env` заполни `DATABASE_URL` адресом Neon. Затем:

   ```bash
   .venv/bin/python scripts/migrate_sqlite.py /path/to/current/bot.db
   ```

Скрипт читает SQLite только для чтения, переносит языки и связи обращений одной
транзакцией. Повторный запуск не перезаписывает уже существующие строки. Старое
состояние ожидания сообщения было в памяти, перенести его нельзя. Если данных нет,
миграцию можно пропустить. Polling со старым токеном нужно остановить в любом случае
перед включением нового webhook.

## 3. Разверни Web Service на Render

Используй ветку **`codex/neon-render-webhook`** репозитория `m4ryjan3/syrlasy_bot`.
Подключи GitHub к [Render](https://dashboard.render.com/).

Самый простой способ — **New → Blueprint**, выбрать репозиторий и эту ветку.
В ней есть `render.yaml`: один Docker Web Service в Frankfurt, план Free.
Blueprint запросит `BOT_TOKEN` и `DATABASE_URL`; `WEBHOOK_SECRET` сгенерирует сам.
Перед подтверждением проверь выбранный план и актуальные ограничения Render.

Или создай **New → Web Service** вручную:

| Настройка | Значение |
| --- | --- |
| Repository | `m4ryjan3/syrlasy_bot` |
| Branch | `codex/neon-render-webhook` |
| Language / Runtime | Docker |
| Dockerfile Path | `./Dockerfile` |
| Region | Frankfurt или ближайший к Neon |
| Instances | 1 |
| Health Check Path | `/livez` |

Для Docker отдельно задавать Build Command и Start Command не нужно: их определяет
Dockerfile. Сервис слушает `0.0.0.0:$PORT`; Render задаёт `PORT` автоматически.
Добавь переменные в **Environment**:

| Переменная | Что указать |
| --- | --- |
| `BOT_TOKEN` | Токен бота от BotFather |
| `DATABASE_URL` | Свой Neon URL из шага 1 |
| `BOT_MODE` | `webhook` |
| `AUTO_REGISTER_WEBHOOK` | `true` после переноса базы и остановки старого бота |
| `WEBHOOK_SECRET` | Независимая случайная строка; Blueprint генерирует её автоматически |
| `ADMIN_CHAT_ID` | ID админ-чата; исходное значение `-5571000368` |

При ручной настройке сгенерировать webhook secret на своём компьютере можно так:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Этот секрет отличается от токена BotFather. Бот должен быть добавлен в админ-чат
и иметь право копировать туда сообщения.

Render автоматически предоставляет `RENDER_EXTERNAL_URL`. При
`AUTO_REGISTER_WEBHOOK=true` приложение регистрирует этот адрес + `/webhook`
в Telegram и проверяет сохранённый URL через `getWebhookInfo`. Никаких токенов
в адресной строке браузера и запросов `setWebhook` вручную не требуется.
Pending updates при регистрации сохраняются. Ошибка регистрации приводит к
ошибке запуска: смотри причину в Render Logs, не публикуя содержимое секретов.

Для своего домена можно задать `WEBHOOK_BASE_URL=https://bot.example.com`; он
имеет приоритет над адресом Render. При `AUTO_REGISTER_WEBHOOK=false` приложение
не меняет Telegram webhook; это удобно для подготовки сервиса до переключения.

После Deploy проверь:

- `https://YOUR-SERVICE.onrender.com/livez` → `{"status":"ok"}`: HTTP-процесс отвечает.
- `https://YOUR-SERVICE.onrender.com/healthz` → `{"status":"ok"}`: Neon отвечает.
- В Render Logs есть `Webhook registered`.
- В Telegram: `/start`, оба языка, меню, анонимное/именное обращение, ответ из
  админ-чата и `/change_language`. Это обязательная проверка с настоящим Telegram.

Обработчики выполняются до HTTP-ответа; POST `/webhook` проверяет заголовок
`X-Telegram-Bot-Api-Secret-Token`. Без правильного секрета ответ — 401.

## 4. Настрой UptimeRobot

В [UptimeRobot](https://uptimerobot.com/) создай монитор **HTTP(s)**:

- URL: `https://YOUR-SERVICE.onrender.com/livez`.
- Интервал: 5 минут, если доступен на выбранном плане.
- Ожидаемый код: 200. Включи доступный канал уведомлений.

Проверка `/livez` не делает SQL-запросов. Это монитор HTTP-сервиса, а не проверка
доставки сообщений или работоспособности базы. Для проверки БД есть `/healthz`;
постоянные запросы к нему могут мешать Neon переходить в idle и расходовать лимит
compute. Пинги UptimeRobot также потребляют ресурсы Render.

Бесплатные планы не дают гарантии непрерывной работы: возможны холодные старты,
приостановки, исчерпание квот и задержки первого сообщения. UptimeRobot не отменяет
лимиты Render и Neon и не заменяет проверку бота. Для строгого требования 24/7
выбери тарифы без нужных тебе ограничений. Настрой уведомления и проверяй актуальные
условия провайдеров.

## Разработка и тесты

Нужен Python 3.9 или новее (рекомендуется 3.12) и PostgreSQL 17. Секреты храни в локальном `.env`.
Для разработки используй отдельного Telegram-бота: polling при запуске удаляет
webhook для своего токена, сохраняя pending updates.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
BOT_MODE=polling .venv/bin/python main.py
```

Для одноразовых локальных тестов:

```bash
docker run -d --name syrlasy-test-db \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=syrlasy_test \
  -p 127.0.0.1:55432:5432 postgres:17
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/syrlasy_test \
  .venv/bin/python -m pytest -q
```

Trust-аутентификация предназначена только для локальных тестов на loopback.
Тесты очищают таблицы в `TEST_DATABASE_URL`: никогда не указывай рабочую Neon DB.
Telegram имитируется, реальные сообщения не отправляются.

Если нужна отдельная регистрация без автоматического режима:

```bash
BOT_MODE=register-webhook WEBHOOK_BASE_URL=https://YOUR-SERVICE.onrender.com \
  .venv/bin/python main.py
```

Состояние диалогов переживает перезапуски. Внутри процесса сообщения одного
диалога сериализуются; сохраняй один экземпляр сервиса. Во время redeploy старый
и новый процесс могут ненадолго пересечься: это не распределённая очередь и не
гарантия exactly-once. Повтор Telegram после сетевого сбоя может повторить
пересылку. Для нескольких экземпляров понадобятся межпроцессная сериализация и
защита от повторной доставки.

Секреты и базу не включай в Git. Настрой резервные копии/восстановление согласно
тарифу Neon; ни Render, ни UptimeRobot не заменяют backup пользовательских данных.

## Если pip не находит версию пакета

Сначала проверь версию Python внутри виртуального окружения:

```bash
python3 --version
.venv/bin/python --version
```

Для этого кода нужен Python 3.9 или новее. На Render Dockerfile выбирает 3.12.
После получения актуальной ветки обнови зависимости:

```bash
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Если Python старее 3.9, установи Python 3.12 и создай новое окружение,
сохранив старое и файл `.env`:

```bash
python3.12 -m venv .venv312
.venv312/bin/python -m pip install -r requirements.txt
```

В таком случае для дальнейших локальных команд используй `.venv312/bin/python`.
