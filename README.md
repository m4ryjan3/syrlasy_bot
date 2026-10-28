# Syrlasy bot: Cloud Run + PostgreSQL

Команды, тексты, кнопки и пересылка обращений сохранены. Язык пользователя,
связи сообщений с админ-чатом и FSM (ожидание обращения) хранятся в PostgreSQL.
SQLite в рабочем приложении больше не используется. Схема создаётся при старте;
старый `bot.db` оставлен для переноса данных и исключён из Docker/Cloud Build.

## Локальный запуск

Нужны Python 3.12 и PostgreSQL 17. Из корня репозитория:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
```

Заполни `.env` локально: `BOT_TOKEN` и `DATABASE_URL`. Не коммить этот файл.
Для отдельной локальной базы можно использовать Docker:

```bash
docker run -d --name syrlasy-postgres \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=syrlasy \
  -p 127.0.0.1:5432:5432 -v syrlasy-pgdata:/var/lib/postgresql/data postgres:17
```

Это **только локальная разработка**: доверительная аутентификация на loopback.
URL: `postgresql://postgres@127.0.0.1:5432/syrlasy`.
В облаке нужна отдельная база с паролем и резервными копиями.

```bash
BOT_MODE=polling .venv/bin/python main.py
```

Polling удаляет webhook, сохраняя ожидающие updates. Не запускай его одновременно
с облачным ботом на том же токене. Для разработки лучше отдельный бот BotFather.
`ADMIN_CHAT_ID` необязателен; по умолчанию сохранён исходный `-5571000368`.
Бот должен иметь доступ к этому чату.

Тесты требуют **отдельную одноразовую** БД: они очищают таблицы `users`,
`support_messages`, `fsm_state`. Telegram в тестах имитируется, запросов к нему нет.

```bash
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/syrlasy_test \
  .venv/bin/python -m pytest -q
```

## Google Cloud: первый запуск

Понадобятся Google Cloud project, подключённый billing и `gcloud` с доступом к
проекту. Cloud SQL оплачивается и при отсутствии запросов к боту. Пример ниже —
однозонный небольшой экземпляр с ежедневным backup и PITR; это не HA-конфигурация.
Перед созданием проверь актуальные тарифы и подходящий регион.

Выполняй из корня репозитория. Подставь свой project ID:

```bash
export PROJECT_ID=your-project-id
export REGION=europe-west1
export SERVICE=syrlasy-bot
export INSTANCE=syrlasy-db
export CONNECTION_NAME="$PROJECT_ID:$REGION:$INSTANCE"
export RUNTIME_SA="syrlasy-runtime@$PROJECT_ID.iam.gserviceaccount.com"
gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

gcloud iam service-accounts create syrlasy-runtime

gcloud sql instances create "$INSTANCE" --region="$REGION" \
  --database-version=POSTGRES_17 --edition=ENTERPRISE --tier=db-custom-1-3840 \
  --storage-size=10 --storage-auto-increase --backup-start-time=02:00 \
  --enable-point-in-time-recovery

gcloud sql databases create syrlasy --instance="$INSTANCE"
```

В Console → Cloud SQL → Users создай пользователя `syrlasy` с сильным паролем.
Не добавляй `0.0.0.0/0` в authorized networks: Cloud Run использует управляемое
соединение Cloud SQL через Unix socket и IAM `Cloud SQL Client`.

В Secret Manager создай три секрета и добавь версии значений через Console:

| Имя секрета | Значение |
| --- | --- |
| `syrlasy-bot-token` | Токен BotFather |
| `syrlasy-database-url` | `postgresql://syrlasy:PASSWORD@/syrlasy?host=/cloudsql/PROJECT:REGION:INSTANCE` |
| `syrlasy-webhook-secret` | Независимая случайная строка, например результат `python -c 'import secrets; print(secrets.token_urlsafe(32))'` |

В DATABASE_URL замени PROJECT, REGION, INSTANCE и пароль. Спецсимволы пароля
должны быть percent-encoded как URL userinfo. WEBHOOK_SECRET — отдельный секрет,
не токен Telegram. Не вставляй значения секретов в Git или команды деплоя.

Выдай runtime service account доступ только к этим секретам и Cloud SQL:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" --role=roles/cloudsql.client
for secret_name in syrlasy-bot-token syrlasy-database-url syrlasy-webhook-secret; do
  gcloud secrets add-iam-policy-binding "$secret_name" \
    --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
done
```

Собери именно Dockerfile: он не включает базу, `.env` и секреты.

```bash
gcloud artifacts repositories create syrlasy --repository-format=docker --location="$REGION"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/syrlasy/bot:v1"
gcloud builds submit --tag "$IMAGE" .
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" \
  --service-account="$RUNTIME_SA" --allow-unauthenticated \
  --add-cloudsql-instances="$CONNECTION_NAME" \
  --set-env-vars=BOT_MODE=webhook \
  --set-secrets=BOT_TOKEN=syrlasy-bot-token:1,DATABASE_URL=syrlasy-database-url:1,WEBHOOK_SECRET=syrlasy-webhook-secret:1 \
  --concurrency=1 --max-instances=1 --min-instances=0 \
  --memory=512Mi --cpu=1 --timeout=60
export SERVICE_URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
curl --fail "$SERVICE_URL/healthz"
```

Если версии секретов отличаются от `1`, укажи существующие номера. Cloud Build
service account нужны права сборки и записи в Artifact Registry; конкретная
учётная запись зависит от настроек проекта. При IAM-ошибке выдай недостающее
право используемому аккаунту, не runtime-боту.

Публичный Cloud Run нужен Telegram; POST `/webhook` защищён проверкой заголовка
`X-Telegram-Bot-Api-Secret-Token`. Токен бота не находится в URL сервиса.
`/healthz` возвращает 200, только когда PostgreSQL отвечает.

После успешного запуска **отдельно зарегистрируй webhook**. На своём компьютере
в `.env` должны быть тот же `BOT_TOKEN` и `WEBHOOK_SECRET`, что в Secret Manager:

```bash
BOT_MODE=register-webhook WEBHOOK_BASE_URL="$SERVICE_URL" .venv/bin/python main.py
```

Команда вызывает `setWebhook` и проверяет сохранённый URL через `getWebhookInfo`.
Она не отправляет сообщения пользователям и не удаляет pending updates.
После этого отправь `/start`, выбери язык, проверь меню, анонимное/именное
обращение и ответ из админ-чата. Эти проверки с реальным Telegram обязательны
перед использованием; локальные тесты их не заменяют.

### Перенос старой базы

Останови старый polling и не регистрируй новый webhook до завершения переноса.
Сделай резервную копию актуального `bot.db` со старого сервера. Файл из Git может
быть устаревшим. Для подключения к Cloud SQL с компьютера используй официальный
[Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy)
с учётной записью, имеющей `Cloud SQL Client`:

```bash
cloud-sql-proxy --address 127.0.0.1 --port 5433 "$CONNECTION_NAME"
```

В другом терминале установи в локальном `.env` PostgreSQL URL для
`127.0.0.1:5433` с тем же пользователем и паролем (без параметра socket `host`), затем:

```bash
.venv/bin/python scripts/migrate_sqlite.py /path/to/current/bot.db
```

Переносятся языки и связи обращений. Скрипт читает SQLite только для чтения и
вносит данные в PostgreSQL одной транзакцией. Повторный запуск не перезаписывает
существующие строки. Старое состояние ожидания сообщения было в памяти и
перенести его невозможно. После переноса зарегистрируй webhook.

### Эксплуатация

- Не увеличивай concurrency, max instances и `setWebhook.max_connections` без
  добавления межпроцессной сериализации диалогов. При релизе избегай параллельной
  обработки старой и новой ревизиями. Состояние хранится постоянно, но это не
  распределённая очередь и не гарантия exactly-once: повтор Telegram после
  сетевого сбоя может повторить пересылку.
- Updates обрабатываются до HTTP-ответа, без фоновых задач после ответа, что
  совместимо с выделением CPU Cloud Run только на время запроса.
- Холодный старт при min instances=0 возможен; для меньшей задержки можно поставить
  min instances=1, учитывая стоимость. Не используй HTTP liveness probe, зависящий
  от доступности БД, чтобы не перезапускать сервис при временном сбое PostgreSQL.
- Backup/PITR не заменяют проверку восстановления. Настрой budget alerts,
  мониторинг ошибок Cloud Run, Cloud SQL и `getWebhookInfo.last_error_message`.
- Сервис сам webhook при старте не меняет. При изменении URL или webhook secret
  повтори регистрацию. При ротации версий секретов обнови конфигурацию сервиса.
