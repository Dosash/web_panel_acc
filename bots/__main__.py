"""Запуск встроенного бота отдельным процессом: python -m bots posts|ads.

Так их запускает TG Panel (app/bots.py); в программе для ПК — tg-panel --bot posts|ads.
Панель держит открытым stdin бота: когда панель завершается (даже аварийно), stdin закрывается
и бот выходит сам — второй процесс с тем же токеном не останется висеть.
"""
import asyncio
import os
import sys
import threading

NAMES = ("posts", "ads")


def _exit_with_parent() -> None:
    # os.read, а не sys.stdin.buffer.read: буферизованный stdin держит замок, и когда бот выходит сам
    # (неверный токен), интерпретатор при завершении не может его забрать — «Fatal Python error:
    # _enter_buffered_busy» вместо обычного кода выхода
    try:
        while os.read(0, 4096):
            pass
    except Exception:
        pass
    os._exit(0)


def main(name: str) -> None:
    if name not in NAMES:
        sys.exit(f"Неизвестный бот «{name}», есть: {', '.join(NAMES)}")
    if os.getenv("TG_PANEL_CHILD") == "1" and sys.stdin is not None:
        threading.Thread(target=_exit_with_parent, name="parent-watch", daemon=True).start()
    # без runpy: в сборке PyInstaller модули лежат в архиве, прямой импорт надёжнее
    if name == "posts":
        from bots.posts.__main__ import main as run
        sys.exit(run())
    from bots.ads.__main__ import main as run
    asyncio.run(run())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
