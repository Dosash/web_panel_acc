"""Сервер панели — тот же FastAPI из app/ — в фоновом потоке на 127.0.0.1."""
import logging
import socket
import sys
import threading

log = logging.getLogger("desktop.server")


def free_port(preferred: int = 0) -> int:
    """Прошлый порт, если свободен: от порта зависит origin страницы, а с ним — настройки
    интерфейса в localStorage (тема, невидимка). Иначе любой свободный."""
    for port in (preferred, 0) if preferred else (0,):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if sys.platform != "win32":
                # как у uvicorn: соединения прошлого запуска в TIME_WAIT не мешают занять порт снова
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise RuntimeError("Нет свободного порта на 127.0.0.1")


class PanelServer:
    """Импорт app.main (Telethon, opentele) занимает пару секунд — делаем его в потоке сервера,
    чтобы окно появилось сразу. Переменные окружения для app.config выставляет launcher заранее."""

    def __init__(self, port: int):
        self.port = port
        self.url = f"http://127.0.0.1:{port}/"
        self.cookie: tuple[str, str] | None = None  # (имя, значение) cookie входа в панель
        self.error: str | None = None
        self._server = None
        self._thread = threading.Thread(target=self._run, name="panel-server", daemon=True)

    def start(self) -> None:
        self._thread.start()

    @property
    def started(self) -> bool:
        return bool(self._server and self._server.started)

    @property
    def failed(self) -> bool:
        return self.error is not None or (not self._thread.is_alive() and not self.started)

    def _run(self) -> None:
        try:
            import uvicorn

            from app.main import COOKIE, app, signer

            self.cookie = (COOKIE, signer.dumps("admin"))
            # log_config=None: журнал уже настроен в launcher; uvicorn иначе пишет в stdout, которого
            # у оконной программы под Windows нет
            config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_config=None,
                                    timeout_graceful_shutdown=5)
            self._server = uvicorn.Server(config)
            self._server.run()
        except BaseException as e:  # opentele и uvicorn (sys.exit при занятом порте) бросают не только Exception
            self.error = f"{type(e).__name__}: {e}"
            log.exception("Сервер панели остановился с ошибкой")

    def stop(self, timeout: float = 15) -> None:
        """Отключает аккаунты (lifespan панели) и останавливает сервер."""
        if self._server:
            self._server.should_exit = True
        self._thread.join(timeout)
