"""Серверная часть TG Panel для Windows (desktop-win): сервер панели из app/ на 127.0.0.1 отдельным процессом.

Его запускает оболочка (desktop-win/shell, TG Panel.exe) в режиме «на этом компьютере»:

    tg-panel-server.exe --data <папка данных> [--port <прошлый порт>]

Протокол с оболочкой — строки JSON в stdout:
    {"event": "ready", "port": 54321, "cookie": ["panel_auth", "<значение>"]}   сервер принимает запросы
    {"event": "error", "message": "…"}                                            не запустился
Журнал (logging) — в stderr: оболочка пишет его в <данные>\\logs\\tg-panel.log.
Выход: строка «quit» в stdin или закрытый stdin (оболочка закрылась или упала) — lifespan панели штатно
отключает аккаунты и ботов, затем процесс завершается.

Тот же exe запускает встроенных ботов: app/bots.py в сборке вызывает [sys.executable, "--bot", имя].
tg-panel-server.exe --self-test — проверка сборки: импорт панели и чтение tdata через opentele (PyQt5.QtCore)."""
import json
import logging
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(HERE.parents[1]))  # app/ и bots/ из корня репозитория

log = logging.getLogger("server")


def open_std_streams() -> None:
    """У сборки без консоли sys.stdin/stdout/stderr — None, хотя оболочка (и панель для ботов) передаёт
    каналы: открываем их сами (как launcher.run_bot в desktop/)."""
    for fd, attr, mode in ((0, "stdin", "r"), (1, "stdout", "w"), (2, "stderr", "w")):
        if getattr(sys, attr) is None:
            try:
                setattr(sys, attr, os.fdopen(fd, mode, encoding="utf-8", errors="replace", buffering=1))
            except OSError:
                # без stdin не узнать о выходе оболочки — но и devnull не годится: конец файла сразу
                setattr(sys, attr, None if fd == 0 else open(os.devnull, mode, encoding="utf-8"))
        elif fd:
            getattr(sys, attr).reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def emit(**event) -> None:
    """Сообщение оболочке — одна строка JSON в stdout (ASCII: кодировка канала не важна)."""
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def free_port(preferred: int = 0) -> int:
    """Прошлый порт, если свободен: от порта зависит origin страницы, а с ним — настройки
    интерфейса в localStorage (тема, невидимка). Иначе любой свободный."""
    for port in (preferred, 0) if preferred else (0,):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise RuntimeError("Нет свободного порта на 127.0.0.1")


def run_bot(name: str) -> int:
    """tg-panel-server --bot posts|ads: встроенный бот, которого запускает панель (app/bots.py)."""
    from bots.__main__ import main as bot_main
    bot_main(name)
    return 0


class Control:
    """Текущий uvicorn.Server и просьба оболочки выйти (она может прийти и до запуска сервера)."""
    server = None
    stop = threading.Event()


def watch_stdin() -> None:
    """«quit» или конец stdin — штатный выход: uvicorn завершит lifespan панели (аккаунты отключатся)."""
    try:
        for line in sys.stdin:
            if line.strip() == "quit":
                break
    except (OSError, ValueError):
        pass
    log.info("Оболочка просит выйти — останавливаем сервер")
    Control.stop.set()
    if Control.server is not None:
        Control.server.should_exit = True


def wait_started(server, port: int, cookie: tuple[str, str]) -> None:
    while not server.should_exit:
        if server.started:
            emit(event="ready", port=port, cookie=list(cookie))
            return
        time.sleep(0.05)


def serve(data: Path, preferred: int) -> int:
    # настройки для app.config — до импорта app. Пароль случайный на каждый запуск: вход выполняет
    # оболочка (cookie), а другие программы на компьютере в панель не попадут
    os.environ.update(DATA_DIR=str(data), WEB_HOST="127.0.0.1", WEB_PREFIX="",
                      WEB_PASSWORD=secrets.token_urlsafe(32))
    try:
        import uvicorn

        from app.main import COOKIE, app, signer
    except BaseException as e:  # opentele бросает BaseException (см. app/tdata_import._reraise_fatal)
        log.exception("Не удалось загрузить панель")
        emit(event="error", message=f"Не удалось загрузить панель: {type(e).__name__}: {e}")
        return 1
    cookie = (COOKIE, signer.dumps("admin"))
    for attempt, wanted in enumerate((preferred, 0) if preferred else (0,)):
        if Control.stop.is_set():
            return 0
        port = free_port(wanted)
        # log_config=None: журнал настроен здесь (stderr → оболочка); timeout — сколько ждать открытые
        # соединения (WebSocket страницы) при выходе, прежде чем закрыть их
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, timeout_graceful_shutdown=5)
        server = Control.server = uvicorn.Server(config)
        server.should_exit = Control.stop.is_set()  # «quit» пришёл, пока сервер создавался
        threading.Thread(target=wait_started, args=(server, port, cookie), name="ready", daemon=True).start()
        log.info("TG Panel: данные %s, порт %s", data, port)
        try:
            server.run()
        except SystemExit:  # uvicorn выходит так, если порт успели занять между проверкой и запуском
            pass
        except BaseException as e:
            log.exception("Сервер панели остановился с ошибкой")
            emit(event="error", message=f"{type(e).__name__}: {e}")
            return 1
        if server.started or Control.stop.is_set():
            return 0
        if attempt == 0 and preferred:
            log.warning("Порт %s занят — берём другой", port)
    emit(event="error", message="Сервер панели не запустился — подробности в журнале")
    return 1


def self_test() -> int:
    """Проверка собранной программы без сети: панель импортируется, tdata пишется и читается (QtCore)."""
    import tempfile

    from opentele.api import API
    from opentele.td import Account, AuthKey, AuthKeyType, TDesktop
    from opentele.td.configs import DcId

    with tempfile.TemporaryDirectory(prefix="tg-panel-selftest-") as tmp:
        os.environ.update(DATA_DIR=str(Path(tmp) / "data"), WEB_HOST="127.0.0.1", WEB_PREFIX="",
                          WEB_PASSWORD="selftest")
        import app.main  # noqa: F401 — весь сервер панели со всеми модулями
        from app.tdata_import import convert  # noqa: F401

        key = os.urandom(256)
        owner = TDesktop()
        account = Account(owner=owner, api=API.TelegramDesktop, index=0)
        account._setMtpAuthorizationCustom(DcId(2), 123456789, [AuthKey(key, AuthKeyType.ReadFromFile, DcId(2))])
        owner._addSingleAccount(account)
        tdata = Path(tmp) / "tdata"
        owner.SaveTData(str(tdata), passcode="selftest")
        loaded = TDesktop(str(tdata), passcode="selftest")
        ok = loaded.accountsCount == 1 and loaded.accounts[0].authKey.key == key \
            and loaded.accounts[0].UserId == 123456789
    print("self-test:", "ok" if ok else "tdata прочитана неверно")
    return 0 if ok else 1


def main() -> int:
    open_std_streams()
    args = sys.argv[1:]
    if "--bot" in args:  # журнал бот настраивает сам
        i = args.index("--bot")
        return run_bot(args[i + 1] if i + 1 < len(args) else "")
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--self-test" in args:
        return self_test()
    opts = dict(zip(args[::2], args[1::2]))
    data = opts.get("--data") or os.getenv("TG_PANEL_DATA", "")
    if not data.strip():
        emit(event="error", message="Не указана папка данных (--data)")
        return 2
    data = Path(data).expanduser().resolve()
    data.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=watch_stdin, name="stdin-watch", daemon=True).start()
    return serve(data, int(opts.get("--port") or 0))


if __name__ == "__main__":
    sys.exit(main())
