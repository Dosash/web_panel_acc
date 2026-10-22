#!/usr/bin/env bash
# Запуск панели: создаёт окружение при первом запуске и стартует сервер
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  # opentele тянет PyQt5, который стабильно ставится на Python 3.12
  if command -v uv >/dev/null; then
    uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
  else
    python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
  fi
fi
if [ ! -f .env ]; then
  cp .env.example .env
fi
set -a; source .env; set +a
exec .venv/bin/uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}"
