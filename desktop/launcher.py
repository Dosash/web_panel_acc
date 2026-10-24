"""TG Panel для Windows, Linux и macOS: сервер панели из app/ на 127.0.0.1 + окно со встроенным браузером.

Запуск из исходников: python desktop/launcher.py [--hidden]
Папка данных: см. paths.data_dir() или переменная TG_PANEL_DATA.
TG_PANEL_SERVER=http://сервер/accounts/ — при первом запуске сразу подключиться к своему серверу, без вопроса."""
import hashlib
import logging
import logging.handlers
import os
import secrets
import signal
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if not getattr(sys, "frozen", False):
    sys.path[:0] = [str(HERE), str(HERE.parent)]  # app/ из корня репозитория

import paths  # noqa: E402

log = logging.getLogger("desktop")


def setup_logging(data: Path) -> Path:
    """Журнал в файл — у оконной программы под Windows нет консоли (sys.stdout = None)."""
    logs = data / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "tg-panel.log"
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    else:
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")  # print() в библиотеках не упадёт
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return path


def prepare_environment(data: Path) -> None:
    # настройки для app.config — до импорта app. Пароль случайный на каждый запуск: вход выполняет
    # само приложение (cookie), а другие программы на компьютере в панель не попадут
    os.environ.update(DATA_DIR=str(data), WEB_HOST="127.0.0.1", WEB_PREFIX="",
                      WEB_PASSWORD=secrets.token_urlsafe(32))
    if sys.platform.startswith("linux"):
        # Qt 5 WebEngine под Wayland работает нестабильно — через XWayland надёжнее
        if os.getenv("DISPLAY") and "TG_PANEL_WAYLAND" not in os.environ:
            os.environ["QT_QPA_PLATFORM"] = "xcb"
        # Ubuntu 23.10+ запрещает непривилегированные user namespaces — без них песочница Chromium
        # не стартует и окно остаётся пустым
        flag = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
        try:
            if flag.read_text().strip() == "1":
                os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        except OSError:
            pass
    if sys.platform == "win32":
        import ctypes
        # свой значок и группа на панели задач, имя в уведомлениях
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TGPanel.Desktop")


def run_bot(name: str) -> int:
    """tg-panel --bot posts|ads: встроенный бот, которого запускает панель (app/bots.py), — без окна.
    У оконной сборки под Windows sys.stdin/stdout — None, хотя панель передаёт каналы: открываем их сами."""
    for fd, attr, mode in ((0, "stdin", "r"), (1, "stdout", "w"), (2, "stderr", "w")):
        if getattr(sys, attr) is None:
            try:
                setattr(sys, attr, os.fdopen(fd, mode, encoding="utf-8", errors="replace", buffering=1))
            except OSError:
                # без stdin бот не узнает о выходе панели — но и devnull не годится: конец файла сразу
                setattr(sys, attr, None if fd == 0 else open(os.devnull, mode, encoding="utf-8"))
    from bots.__main__ import main as bot_main
    bot_main(name)
    return 0


def main() -> int:
    if "--bot" in sys.argv:
        i = sys.argv.index("--bot")
        return run_bot(sys.argv[i + 1] if i + 1 < len(sys.argv) else "")
    start_hidden = "--hidden" in sys.argv
    data = paths.data_dir()
    data.mkdir(parents=True, exist_ok=True)
    log_path = setup_logging(data)
    prepare_environment(data)

    from PyQt5.QtCore import QCoreApplication, QSettings, Qt, QTimer
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    from PyQt5 import QtWebEngineWidgets  # noqa: F401 — до QApplication, иначе WebEngine не стартует

    from connection import LOCAL, REMOTE, ConnectionDialog, normalize_url
    from server import PanelServer, free_port
    from shell import ShellWindow, app_icon
    from single import SingleInstance

    qt = QApplication(sys.argv[:1])
    qt.setApplicationName(paths.APP_NAME)
    qt.setApplicationDisplayName(paths.APP_NAME)
    qt.setOrganizationName(paths.APP_NAME)
    qt.setDesktopFileName(paths.APP_ID)

    # одна копия на папку данных: две копии подключили бы одни и те же сессии дважды
    instance = SingleInstance("tg-panel-" + hashlib.sha1(str(data).encode()).hexdigest()[:12])
    if instance.forward_to_running():
        log.info("Приложение уже запущено — показываем его окно")
        return 0

    settings = QSettings(str(data / "desktop.ini"), QSettings.IniFormat)
    mode = settings.value("mode", "")
    if mode not in (LOCAL, REMOTE):
        preset = os.getenv("TG_PANEL_SERVER", "").strip()
        if preset:
            mode, url = REMOTE, normalize_url(preset)
        else:
            # первый запуск: где работают аккаунты
            dialog = ConnectionDialog()
            dialog.setWindowIcon(app_icon())
            if dialog.exec_() != ConnectionDialog.Accepted:
                return 0
            mode, url = dialog.result_value()
        settings.setValue("mode", mode)
        if url:
            settings.setValue("server_url", url)

    version = paths.version()
    server = None
    if mode == LOCAL:
        port = free_port(int(settings.value("port", 0) or 0))
        settings.setValue("port", port)
        log.info("TG Panel desktop %s: данные %s, порт %s", version, data, port)
        server = PanelServer(port)
        server.start()
    else:
        log.info("TG Panel desktop %s: сервер %s", version, settings.value("server_url"))
    window = ShellWindow(settings, data, mode, version, start_hidden=start_hidden)
    qt.setQuitOnLastWindowClosed(window.tray is None)
    instance.activated.connect(window.show_window)
    # macOS: щелчок по значку в доке, когда окно скрыто
    qt.applicationStateChanged.connect(
        lambda state: window.show_window() if sys.platform == "darwin" and state == Qt.ApplicationActive
        and not window.isVisible() and not window.quitting else None)

    # Ctrl+C в терминале, завершение сеанса: выходим как через «Выход» — с отключением аккаунтов.
    # Пока крутится цикл Qt, Python видит сигнал только между вызовами — отсюда пустой таймер
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: QTimer.singleShot(0, window.quit))
    ticker = QTimer()
    ticker.timeout.connect(lambda: None)
    ticker.start(500)

    def wait_server():
        if server is None:
            window.load_remote(str(settings.value("server_url")))
        elif server.started:
            window.load_panel(server.url, server.cookie)
        elif server.failed:
            window.show_error("Не удалось запустить панель",
                              f"{server.error or 'Сервер остановился'}\n\nПодробности в журнале:\n{log_path}")
        else:
            QTimer.singleShot(100, wait_server)

    wait_server()
    code = qt.exec_()
    if server:
        log.info("Выход: отключаем аккаунты")
        server.stop()
    instance.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
