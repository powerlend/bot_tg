#!/bin/sh
# Запуск бота в контейнері.
# 1) Якщо налаштовано Litestream: відновлює базу з хмари, потім запускає бота
#    разом з постійною реплікацією бази.
# 2) Якщо ні: просто запускає бота (база зникне при перезапуску сервісу).
set -e

export DB_PATH="${DB_PATH:-/app/data/bot.db}"
export LITESTREAM_PATH="${LITESTREAM_PATH:-bot-db}"
mkdir -p "$(dirname "$DB_PATH")"

if [ -z "$LITESTREAM_BUCKET" ]; then
  echo "[entrypoint] УВАГА: LITESTREAM_BUCKET не задано. Бот запускається БЕЗ реплікації бази: при перезапуску сервісу дані зникнуть."
  exec python bot.py
fi

for var in LITESTREAM_ENDPOINT LITESTREAM_ACCESS_KEY_ID LITESTREAM_SECRET_ACCESS_KEY; do
  eval "value=\${$var}"
  if [ -z "$value" ]; then
    echo "[entrypoint] ПОМИЛКА: не задано змінну $var"
    exit 1
  fi
done

echo "[entrypoint] Відновлюю базу з хмари (якщо вона там є)..."
# Якщо тут станеться помилка, бот НЕ запускається: інакше він створив би порожню базу
# і замінив нею збережену в хмарі.
litestream restore -config /app/litestream.yml -if-db-not-exists -if-replica-exists "$DB_PATH"

echo "[entrypoint] Запускаю бота з реплікацією бази в хмару"
exec litestream replicate -config /app/litestream.yml -exec "python bot.py"
