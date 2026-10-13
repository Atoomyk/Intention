#!/usr/bin/env bash
# Intention — запуск web-API на Linux-сервере.
# Первый раз: chmod +x run_web.sh
# Обычно запускается от пользователя сервиса, например: sudo -u intention /opt/intention/run_web.sh
# Наружу порт не открываем: 127.0.0.1 + nginx (TLS) впереди.
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Не найден $PYTHON_BIN. Установите: sudo apt install python3 python3-venv" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> Создаю виртуальное окружение .venv"
  "$PYTHON_BIN" -m venv .venv
fi

echo "==> Ставлю зависимости (server/requirements.txt)"
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r server/requirements.txt

echo "==> Готовлю каталог данных data/"
mkdir -p data
chmod 700 data 2>/dev/null || true

echo "==> Запускаю uvicorn на http://${HOST}:${PORT} (снаружи — через nginx)"
exec ./.venv/bin/python -m uvicorn server.app:app \
  --host "$HOST" --port "$PORT" \
  --proxy-headers --forwarded-allow-ips=127.0.0.1
