"""Окно приложения: встроенный браузер Qt WebEngine с интерфейсом панели, значок в трее, уведомления,
сохранение файлов, ссылки во внешнем браузере, автозапуск, подключение к серверу, обновления."""
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QDateTime, QSettings, Qt, QTimer, QUrl
from PyQt5.QtGui import QDesktopServices, QIcon, QKeySequence, QPainter, QPixmap
from PyQt5.QtNetwork import QNetworkCookie
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (QAction, QApplication, QFileDialog, QMainWindow, QMenu, QMessageBox, QShortcut,
                             QSystemTrayIcon)
from PyQt5.QtWebEngineWidgets import (QWebEngineDownloadItem, QWebEnginePage, QWebEngineProfile, QWebEngineScript,
                                      QWebEngineSettings, QWebEngineView)

import autostart
import updater
from connection import LOCAL, REMOTE, ConnectionDialog
from paths import APP_NAME, resource

log = logging.getLogger("desktop")

ZOOM_STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]
UPDATE_PATH = "/tg-desktop/update"

# Встраивается в страницу панели. Браузер шлёт уведомление, только когда вкладка скрыта; у приложения
# «скрыто» — это ещё и окно не в фокусе. Выход из панели в локальном режиме не нужен: вход выполняет
# само приложение (на своём сервере пароль вводится как обычно, и кнопка выхода остаётся).
# TG_DESKTOP_APP — версия и режим программы для значка «Вышло обновление»: кнопка «Обновить программу»
# переходит на адрес панели …/UPDATE_PATH, переход ловит Page.acceptNavigationRequest (свою схему
# вроде tg-panel:// WebEngine до acceptNavigationRequest не доводит).
PAGE_SCRIPT = """
(() => {
  window.TG_DESKTOP = true;
  window.TG_DESKTOP_APP = APP_INFO;
  const real = Object.getOwnPropertyDescriptor(Document.prototype, "visibilityState");
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get() { return window.__tgDesktopActive === false ? "hidden" : real.get.call(document); },
  });
  if (!HIDE_LOGOUT) return;
  const style = () => {
    const s = document.createElement("style");
    s.textContent = "#logout { display: none !important; }";
    document.head.appendChild(s);
  };
  if (document.head) style(); else document.addEventListener("DOMContentLoaded", style);
})();
"""


def app_icon() -> QIcon:
    """Значок из icon.svg во всех размерах — без плагинов Qt для svg."""
    renderer = QSvgRenderer(str(resource("icon.svg")))
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        icon.addPixmap(pm)
    return icon


def status_html(title: str, text: str = "", spinner: bool = True) -> str:
    """Экран до загрузки панели: «Запуск…» или ошибка. Цвета — как у тёмной темы панели."""
    spin = '<div class="spin"></div>' if spinner else ""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><style>
html, body {{ height: 100%; margin: 0; background: #0b1220; color: #e6ebf5;
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
body {{ display: grid; place-items: center; text-align: center; }}
.box {{ max-width: 560px; padding: 24px; }}
h1 {{ font-size: 20px; font-weight: 600; margin: 16px 0 6px; }}
p {{ color: #8b98b3; margin: 0; white-space: pre-wrap; word-break: break-word; }}
.spin {{ width: 36px; height: 36px; margin: auto; border-radius: 50%; border: 3px solid #1f2b44;
  border-top-color: #4f8cff; animation: r .9s linear infinite; }}
@keyframes r {{ to {{ transform: rotate(360deg); }} }}
</style></head><body><div class="box">{spin}<h1>{title}</h1><p>{text}</p></div></body></html>"""


def same_origin(a: QUrl, b: QUrl) -> bool:
    return (a.scheme(), a.host(), a.port()) == (b.scheme(), b.host(), b.port())


class Page(QWebEnginePage):
    """Страница панели. Внешние ссылки в главном окне и новые окна — через ShellWindow.open_url."""

    def __init__(self, profile: QWebEngineProfile, shell: "ShellWindow", parent=None):
        super().__init__(profile, parent)
        self.shell = shell
        self.featurePermissionRequested.connect(self.on_permission)
        self.fullScreenRequested.connect(self.on_fullscreen)

    def acceptNavigationRequest(self, url: QUrl, kind, is_main_frame: bool) -> bool:
        if is_main_frame and self.shell.is_panel_url(url) and url.path().endswith(UPDATE_PATH):
            # «Обновить программу» в окне обновления панели
            QTimer.singleShot(0, lambda: self.shell.check_updates(manual=True))
            return False
        # во фреймах (мини-приложения ботов) переходы свои — не трогаем
        if not is_main_frame or url.scheme() in ("data", "about", "blob") or self.shell.is_panel_url(url):
            return True
        self.shell.open_url(url)
        return False

    def createWindow(self, kind):
        # target="_blank", window.open: адрес станет известен при первой навигации новой страницы
        return PopupCatcher(self.profile(), self.shell, self)

    def javaScriptConsoleMessage(self, level, message, line, source):
        # в журнал: ошибка в app.js (например, синтаксис, которого не знает встроенный Chromium) — пустое окно
        if level == QWebEnginePage.ErrorMessageLevel:
            log.warning("js: %s (%s:%s)", message, source, line)

    def on_permission(self, origin: QUrl, feature) -> None:
        if feature == QWebEnginePage.Notifications:
            self.setFeaturePermission(origin, feature, QWebEnginePage.PermissionGrantedByUser)
            return
        names = {
            QWebEnginePage.Geolocation: "местоположению",
            QWebEnginePage.MediaAudioCapture: "микрофону",
            QWebEnginePage.MediaVideoCapture: "камере",
            QWebEnginePage.MediaAudioVideoCapture: "камере и микрофону",
        }
        what = names.get(feature)
        allowed = what and QMessageBox.question(
            self.shell, APP_NAME, f"{origin.host() or origin.toString()} просит доступ к {what}. Разрешить?",
        ) == QMessageBox.Yes
        self.setFeaturePermission(origin, feature, QWebEnginePage.PermissionGrantedByUser if allowed
                                  else QWebEnginePage.PermissionDeniedByUser)

    def on_fullscreen(self, request) -> None:
        request.accept()
        window = self.view().window() if self.view() else self.shell
        window.showFullScreen() if request.toggleOn() else window.showNormal()


class PopupCatcher(QWebEnginePage):
    """Временная страница для «нового окна»: узнаёт адрес и отдаёт его ShellWindow.open_url."""

    def __init__(self, profile, shell: "ShellWindow", parent=None):
        super().__init__(profile, parent)
        self.shell = shell
        self.done = False

    def acceptNavigationRequest(self, url: QUrl, kind, is_main_frame: bool) -> bool:
        if not self.done and url.scheme() not in ("about", ""):
            self.done = True
            self.shell.open_url(url, popup=True)
            QTimer.singleShot(0, self.deleteLater)
        return False


class View(QWebEngineView):
    """Своё контекстное меню: убираем «Назад», «Вперёд», «Исходный код» — у приложения нет вкладок."""

    HIDDEN = (QWebEnginePage.Back, QWebEnginePage.Forward, QWebEnginePage.ViewSource, QWebEnginePage.SavePage,
              QWebEnginePage.OpenLinkInNewTab, QWebEnginePage.OpenLinkInNewWindow,
              QWebEnginePage.OpenLinkInThisWindow, QWebEnginePage.DownloadLinkToDisk)

    def contextMenuEvent(self, event):
        menu = self.page().createStandardContextMenu()
        hidden = {self.page().action(a) for a in self.HIDDEN}
        for action in menu.actions():
            if action in hidden:
                menu.removeAction(action)
        # разделители, оставшиеся в начале, в конце или подряд
        prev_sep = True
        for action in menu.actions():
            if action.isSeparator() and prev_sep:
                menu.removeAction(action)
            prev_sep = action.isSeparator()
        if menu.actions() and menu.actions()[-1].isSeparator():
            menu.removeAction(menu.actions()[-1])
        if menu.actions():
            menu.exec_(event.globalPos())  # не popup: меню без родителя удалил бы сборщик мусора


class ViewerWindow(QMainWindow):
    """Отдельное окно для файлов панели, открытых «в новой вкладке» (фото, видео)."""

    def __init__(self, shell: "ShellWindow", url: QUrl):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowIcon(shell.windowIcon())
        self.setWindowTitle(APP_NAME)
        self.view = View(self)
        self.view.setPage(Page(shell.profile, shell, self.view))
        self.view.titleChanged.connect(lambda t: self.setWindowTitle(f"{t} — {APP_NAME}" if t else APP_NAME))
        self.view.page().setBackgroundColor(Qt.black)
        self.setCentralWidget(self.view)
        self.resize(1000, 760)
        QShortcut(QKeySequence("Esc"), self, self.close)
        QShortcut(QKeySequence.Close, self, self.close)
        self.view.load(url)


class ShellWindow(QMainWindow):
    def __init__(self, settings: QSettings, data_dir: Path, mode: str, version: str, start_hidden: bool = False):
        super().__init__()
        self.settings = settings
        self.data_dir = data_dir
        self.mode = mode
        self.version = version
        self.base_url: QUrl | None = None
        self.quitting = False
        self.viewers: list[ViewerWindow] = []
        self.restart_args: list[str] | None = None  # перезапуск после выхода (смена подключения)
        self.updater = updater.Updater(version, data_dir / "update")
        self.pending_update: updater.Installer | None = None
        self.update_actions: list[QAction] = []  # пункт в трее и в строке меню
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(380, 480)

        # постоянный профиль: localStorage, cookie, кэш. Родитель — приложение: профиль должен
        # пережить страницы окна, иначе WebEngine ругается при выходе
        self.profile = QWebEngineProfile("tg-panel", QApplication.instance())
        self.profile.setPersistentStoragePath(str(data_dir / "webengine"))
        self.profile.setCachePath(str(data_dir / "webengine-cache"))
        self.profile.setNotificationPresenter(self.present_notification)
        self.profile.downloadRequested.connect(self.on_download)
        script = QWebEngineScript()
        script.setName("tg-desktop")
        hide_logout = "true" if mode == LOCAL else "false"
        app_info = json.dumps({"version": version, "mode": mode, "update": True})
        script.setSourceCode(PAGE_SCRIPT.replace("HIDE_LOGOUT", hide_logout).replace("APP_INFO", app_info))
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        self.profile.scripts().insert(script)
        s = self.profile.settings()
        for attr in (QWebEngineSettings.JavascriptCanAccessClipboard, QWebEngineSettings.JavascriptCanPaste,
                     QWebEngineSettings.FullScreenSupportEnabled, QWebEngineSettings.ScrollAnimatorEnabled,
                     QWebEngineSettings.FocusOnNavigationEnabled):
            s.setAttribute(attr, True)

        self.view = View(self)
        self.page = Page(self.profile, self, self.view)
        self.page.setBackgroundColor(Qt.transparent)
        self.page.renderProcessTerminated.connect(self.on_render_crash)
        self.page.loadFinished.connect(self.on_load_finished)
        self.view.setPage(self.page)
        self.view.setZoomFactor(float(settings.value("zoom", 1.0)))
        self.setCentralWidget(self.view)
        self.page.setHtml(status_html("Запуск…", "Подключаем аккаунты"))

        self.tray = self.make_tray()
        self.make_shortcuts()
        self.restore_geometry()
        self.setup_updates()
        if not (start_hidden and self.tray):
            self.show()

    # ---------- окно ----------

    def restore_geometry(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry is None or not self.restoreGeometry(geometry):
            self.resize(1280, 820)

    def show_window(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_window(self) -> None:
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.show_window()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (event.ActivationChange, event.WindowStateChange):
            active = "true" if self.isActiveWindow() and not self.isMinimized() else "false"
            self.page.runJavaScript(f"window.__tgDesktopActive = {active};")

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        if self.tray and not self.quitting:
            # как Telegram: окно закрывается, аккаунты остаются на связи и присылают уведомления
            event.ignore()
            self.hide()
            if not self.settings.value("tray_hint_shown", False, type=bool):
                self.settings.setValue("tray_hint_shown", True)
                self.notify(APP_NAME, "Панель работает в фоне. Открыть или выйти — через значок в трее.")
            return
        event.accept()
        self.quit()

    def quit(self) -> None:
        self.quitting = True
        self.settings.setValue("geometry", self.saveGeometry())
        try:
            if self.pending_update:
                # обновление, отложенное «до выхода»: ставится после закрытия, программа не запускается
                self.pending_update.launch(relaunch=self.restart_args is not None, args=self.restart_args or [])
            elif self.restart_args is not None:
                updater.restart(self.restart_args, self.data_dir / "update")
        except OSError as e:
            log.error("Не удалось запустить скрипт после выхода: %s", e)
        for v in list(self.viewers):
            v.close()
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    def make_shortcuts(self) -> None:
        pairs = [
            (QKeySequence.Refresh, self.view.reload),
            ("Ctrl+R", self.view.reload),
            (QKeySequence.ZoomIn, lambda: self.zoom(+1)),
            ("Ctrl+=", lambda: self.zoom(+1)),
            (QKeySequence.ZoomOut, lambda: self.zoom(-1)),
            ("Ctrl+0", lambda: self.zoom(0)),
            (QKeySequence.FullScreen, self.toggle_fullscreen),
            ("F11", self.toggle_fullscreen),
            ("Ctrl+Shift+I", self.open_devtools),
            (QKeySequence.Quit, self.quit),
            ("Ctrl+Q", self.quit),
        ]
        # стандартная клавиша на одной ОС совпадает с явной (Quit = Ctrl+Q на Linux): два одинаковых
        # QShortcut Qt считает неоднозначными и не срабатывает ни один
        seen = set()
        for key, slot in pairs:
            seq = QKeySequence(key)
            if seq.isEmpty() or seq.toString() in seen:
                continue
            seen.add(seq.toString())
            QShortcut(seq, self, slot)

    def zoom(self, direction: int) -> None:
        current = self.view.zoomFactor()
        if direction == 0:
            value = 1.0
        elif direction > 0:
            value = next((z for z in ZOOM_STEPS if z > current + 0.01), ZOOM_STEPS[-1])
        else:
            value = next((z for z in reversed(ZOOM_STEPS) if z < current - 0.01), ZOOM_STEPS[0])
        self.view.setZoomFactor(value)
        self.settings.setValue("zoom", value)

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def open_devtools(self) -> None:
        win = QMainWindow(self)
        win.setAttribute(Qt.WA_DeleteOnClose)
        win.setWindowTitle(f"Инструменты разработчика — {APP_NAME}")
        tools = QWebEngineView(win)
        tools.setPage(QWebEnginePage(self.profile, tools))
        self.page.setDevToolsPage(tools.page())
        win.setCentralWidget(tools)
        win.resize(1000, 700)
        win.show()

    # ---------- панель ----------

    def load_panel(self, url: str, cookie: tuple[str, str]) -> None:
        """Cookie входа кладётся в браузер напрямую: пароль панели знает только само приложение."""
        self.base_url = QUrl(url)
        name, value = cookie
        c = QNetworkCookie(name.encode(), value.encode())
        c.setPath("/")
        c.setHttpOnly(True)
        c.setExpirationDate(QDateTime.currentDateTime().addDays(30))
        self.profile.cookieStore().setCookie(c, self.base_url)
        # даём хранилищу cookie применить запись до первого запроса страницы
        QTimer.singleShot(50, lambda: self.view.load(self.base_url))

    def load_remote(self, url: str) -> None:
        """Режим «на моём сервере»: интерфейс и аккаунты — с сервера, вход по паролю панели (если он задан)."""
        self.base_url = QUrl(url)
        self.view.load(self.base_url)

    def on_load_finished(self, ok: bool) -> None:
        # сервер недоступен (выключен, нет сети) — свой экран и повтор, а не страница ошибки Chromium
        if ok or self.mode != REMOTE or self.quitting or not self.base_url:
            return
        if not self.is_panel_url(self.page.requestedUrl()):
            return
        url = self.base_url.toString()
        self.page.setHtml(status_html("Сервер панели недоступен",
                                      f"{url}\nПовторяем подключение каждые 10 секунд…\n\n"
                                      "Сменить адрес — значок в трее → «Подключение…»"))
        QTimer.singleShot(10_000, lambda: self.view.load(self.base_url) if not self.quitting else None)

    def show_error(self, title: str, text: str) -> None:
        self.page.setHtml(status_html(title, text, spinner=False))
        self.show_window()

    def is_panel_url(self, url: QUrl) -> bool:
        # на сервере за общим nginx рядом другие панели: своя — только под путём панели
        return (bool(self.base_url) and same_origin(url, self.base_url)
                and url.path().startswith(self.base_url.path() or "/"))

    def open_url(self, url: QUrl, popup: bool = False) -> None:
        """Файлы панели — в отдельном окне приложения, всё остальное — в системном браузере
        (tg:// — в Telegram, если он установлен)."""
        if self.is_panel_url(url):
            if popup:
                viewer = ViewerWindow(self, url)
                self.viewers.append(viewer)
                viewer.destroyed.connect(lambda *_: self.viewers.remove(viewer) if viewer in self.viewers else None)
                viewer.show()
            return
        if url.scheme() in ("http", "https", "tg", "mailto", "tel"):
            QDesktopServices.openUrl(url)

    def on_render_crash(self, status, code) -> None:
        if status != QWebEnginePage.NormalTerminationStatus and not self.quitting:
            log.warning("Процесс страницы завершился (%s, код %s) — перезагружаем", status, code)
            QTimer.singleShot(1000, self.view.reload)

    # ---------- уведомления ----------

    def present_notification(self, notification) -> None:
        """Уведомления страницы (new Notification(...)) — системные, через трей."""
        self._last_notification = notification  # объект должен жить, пока показан
        notification.show()
        self.notify(notification.title(), notification.message())
        QApplication.alert(self)

    def notify(self, title: str, text: str) -> None:
        if self.tray and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, text, self.windowIcon(), 6000)
        elif sys.platform.startswith("linux") and shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-a", APP_NAME, title, text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------- файлы ----------

    def on_download(self, item: QWebEngineDownloadItem) -> None:
        if item.state() != QWebEngineDownloadItem.DownloadRequested:
            return
        folder = self.settings.value("download_dir") or self.default_download_dir()
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", os.path.join(folder, item.downloadFileName()))
        if not path:
            item.cancel()
            return
        self.settings.setValue("download_dir", os.path.dirname(path))
        item.setDownloadDirectory(os.path.dirname(path))
        item.setDownloadFileName(os.path.basename(path))
        item.finished.connect(lambda: self.on_download_finished(item, path))
        item.accept()

    def on_download_finished(self, item: QWebEngineDownloadItem, path: str) -> None:
        if item.state() == QWebEngineDownloadItem.DownloadCompleted:
            self.notify("Файл сохранён", path)
        elif item.state() == QWebEngineDownloadItem.DownloadInterrupted:
            QMessageBox.warning(self, APP_NAME, f"Не удалось сохранить файл:\n{item.interruptReasonString()}")

    @staticmethod
    def default_download_dir() -> str:
        from PyQt5.QtCore import QStandardPaths
        return QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or str(Path.home())

    # ---------- трей ----------

    def build_menu(self, menu: QMenu) -> QMenu:
        menu.addAction("Открыть TG Panel", self.show_window)
        where = "на этом компьютере" if self.mode == LOCAL else self.base_url_text()
        menu.addAction(f"Подключение: {where}…", self.change_connection)
        menu.addAction("Папка с данными", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_dir))))
        menu.addSeparator()
        self.update_actions.append(menu.addAction("Проверить обновления", lambda: self.check_updates(manual=True)))
        auto = QAction("Обновлять автоматически", menu, checkable=True)
        auto.setChecked(self.auto_update)
        auto.toggled.connect(lambda on: self.settings.setValue("auto_update", on))
        menu.addAction(auto)
        if autostart.supported():
            act = QAction("Запускать при входе в систему", menu, checkable=True)
            act.setChecked(autostart.enabled())
            act.toggled.connect(self.set_autostart)
            menu.addAction(act)
        menu.addSeparator()
        menu.addAction("Выход", self.quit)
        return menu

    def make_tray(self) -> QSystemTrayIcon | None:
        if sys.platform == "darwin" or not QSystemTrayIcon.isSystemTrayAvailable():
            # строка меню: в macOS она своя у каждой программы, а без трея иначе не до чего добраться
            self.build_menu(self.menuBar().addMenu(APP_NAME))
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip(f"{APP_NAME} {self.version}")
        menu = self.build_menu(QMenu())
        tray.setContextMenu(menu)
        self._tray_menu = menu
        tray.activated.connect(lambda reason: self.toggle_window() if reason in (
            QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        tray.messageClicked.connect(self.show_window)
        tray.show()
        return tray

    def set_autostart(self, on: bool) -> None:
        try:
            autostart.set_enabled(on)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Не удалось изменить автозапуск: {e}")

    # ---------- подключение ----------

    def base_url_text(self) -> str:
        return str(self.settings.value("server_url", "") or "сервер")

    def change_connection(self) -> None:
        dialog = ConnectionDialog(self.mode, str(self.settings.value("server_url", "") or ""), self)
        if dialog.exec_() != ConnectionDialog.Accepted:
            return
        mode, url = dialog.result_value()
        if (mode, url) == (self.mode, str(self.settings.value("server_url", "") or "") if mode == REMOTE else ""):
            return
        if mode == LOCAL and self.mode == REMOTE and QMessageBox.question(
                self, APP_NAME, "Аккаунты будут подключаться из этой программы. Не используйте одни и те же "
                "сессии одновременно здесь и на сервере — Telegram может их сбросить. Продолжить?") != QMessageBox.Yes:
            return
        self.settings.setValue("mode", mode)
        if url:
            self.settings.setValue("server_url", url)
        self.settings.sync()
        self.restart_args = []
        self.quit()

    # ---------- обновления ----------

    @property
    def auto_update(self) -> bool:
        return self.settings.value("auto_update", True, type=bool)

    def setup_updates(self) -> None:
        u = self.updater
        u.found.connect(self.on_update_found)
        u.ready.connect(self.on_update_ready)
        u.up_to_date.connect(self.on_up_to_date)
        u.failed.connect(self.on_update_failed)
        self._manual_check = False
        # первая проверка — когда программа уже загрузилась, потом раз в 6 часов
        QTimer.singleShot(30_000, lambda: self.check_updates(manual=False))
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(lambda: self.check_updates(manual=False))
        self._update_timer.start(6 * 3600 * 1000)

    def check_updates(self, manual: bool) -> None:
        if self.pending_update:
            if manual:
                self.ask_install(self.pending_update)
            return
        if not manual and not self.auto_update:
            return
        self._manual_check = manual
        self.updater.check(download=True)

    def on_up_to_date(self, latest: str) -> None:
        if self._manual_check:
            QMessageBox.information(self, APP_NAME, f"У вас последняя версия: {self.version}.")

    def on_update_failed(self, error: str) -> None:
        if self._manual_check:
            QMessageBox.warning(self, APP_NAME, f"Не удалось проверить обновления:\n{error}")

    def on_update_found(self, rel: updater.Release) -> None:
        for action in self.update_actions:
            action.setText(f"Обновить до {rel.version}")
        if self.updater.can_install(rel):
            if self._manual_check:
                self.notify(APP_NAME, f"Скачиваем TG Panel {rel.version}…")
            return  # дальше — on_update_ready, когда файл скачается
        # из исходников, без файла под эту систему или без прав на папку программы — только ссылка
        if self._manual_check or self.settings.value("notified_version") != rel.version:
            self.settings.setValue("notified_version", rel.version)
            if QMessageBox.question(self, APP_NAME, f"Доступна TG Panel {rel.version} (у вас {self.version}).\n"
                                    "Открыть страницу загрузки?") == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(rel.page))

    def on_update_ready(self, installer: updater.Installer) -> None:
        self.pending_update = installer
        for action in self.update_actions:
            action.setText(f"Установить {installer.version} и перезапустить")
        if not self.isVisible() and not self._manual_check:
            # программа в трее — обновляемся сразу и тихо возвращаемся в трей
            log.info("Обновление %s: окно скрыто — устанавливаем сразу", installer.version)
            self.install_update(hidden=True)
            return
        self.ask_install(installer)

    def ask_install(self, installer: updater.Installer) -> None:
        box = QMessageBox(QMessageBox.Information, APP_NAME,
                          f"Обновление TG Panel {installer.version} скачано (у вас {self.version}).", parent=self)
        box.setInformativeText("Программа перезапустится, аккаунты переподключатся сами.")
        now = box.addButton("Перезапустить сейчас", QMessageBox.AcceptRole)
        box.addButton("При выходе", QMessageBox.RejectRole)
        box.exec_()
        if box.clickedButton() is now:
            self.install_update(hidden=False)
        else:
            self.notify(APP_NAME, f"Версия {installer.version} установится, когда вы выйдете из программы.")

    def install_update(self, hidden: bool) -> None:
        self.restart_args = ["--hidden"] if hidden else []
        self.quit()
