"""Запуск панели: python -m app (так же — в Docker и в run.sh)."""
import os
import sys

import uvicorn

from . import updates
from .config import WEB_HOST, WEB_PORT

if __name__ == "__main__":
    # timeout_graceful_shutdown: открытые WebSocket не держат остановку контейнера
    server = uvicorn.Server(uvicorn.Config("app.main:app", host=WEB_HOST, port=WEB_PORT, timeout_graceful_shutdown=5))
    restarting = False

    def restart() -> None:
        """Обновление без Docker (app/updates.py): штатная остановка — аккаунты и боты отключатся — и запуск заново."""
        global restarting
        restarting = True
        server.should_exit = True

    updates.restart = restart
    server.run()
    if restarting:
        os.execv(sys.executable, [sys.executable, "-m", "app", *sys.argv[1:]])
    if not server.started:
        sys.exit(3)   # как uvicorn.run: порт занят или приложение не запустилось
