#!/usr/bin/env bash
# Запуск панели без Docker: при первом запуске создаёт окружение .venv и файл .env.
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
if [ ! -d .venv ]; then
  # opentele тянет PyQt5, который стабильно ставится на Python 3.12
  if command -v uv >/dev/null; then
    uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
  else
    python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
  fi
fi
[ -f .env ] || cp .env.example .env
exec .venv/bin/python -m app "$@"
