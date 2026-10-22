"""Запуск панели: python -m app (так же — в Docker и в run.sh)."""
import uvicorn

from .config import WEB_HOST, WEB_PORT

if __name__ == "__main__":
    # timeout_graceful_shutdown: открытые WebSocket не держат остановку контейнера
    uvicorn.run("app.main:app", host=WEB_HOST, port=WEB_PORT, timeout_graceful_shutdown=5)
