"""Окно приложения: встроенный браузер Qt WebEngine с интерфейсом панели, значок в трее, уведомления,
сохранение файлов, ссылки во внешнем браузере, автозапуск."""
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
from paths import APP_NAME, resource

log = logging.getLogger("desktop")

ZOOM_STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]

# Встраивается в страницу панели. Браузер шлёт уведомление, только когда вкладка скрыта; у приложения
# «скрыто» — это ещё и окно не в фокусе. Выход из панели не нужен: вход выполняет само приложение.
PAGE_SCRIPT = """
(() => {
  window.TG_DESKTOP = true;
  const real = Object.getOwnPropertyDescriptor(Document.prototype, "visibilityState");
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get() { return window.__tgDesktopActive === false ? "hidden" : real.get.call(document); },
  });
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
        # во фреймах (мини-приложения ботов) переходы свои — не трогаем
        if not is_main_frame or url.scheme() in ("data", "about", "blob") or self.shell.is_panel_url(url):
            return True
        self.shell.open_url(url)
        return False

    def createWindow(self, kind):
        # target="_blank", window.open: адрес станет известен при первой навигации новой страницы
        return PopupCatcher(self.profile(), self.shell, self)

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.ErrorMessageLevel:
            log.debug("js: %s (%s:%s)", message, source, line)

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
    def __init__(self, settings: QSettings, data_dir: Path, start_hidden: bool = False):
        super().__init__()
        self.settings = settings
        self.data_dir = data_dir
        self.base_url: QUrl | None = None
        self.quitting = False
        self.viewers: list[ViewerWindow] = []
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
        script.setSourceCode(PAGE_SCRIPT)
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
        self.view.setPage(self.page)
        self.view.setZoomFactor(float(settings.value("zoom", 1.0)))
        self.setCentralWidget(self.view)
        self.page.setHtml(status_html("Запуск…", "Подключаем аккаунты"))

        self.tray = self.make_tray()
        self.make_shortcuts()
        self.restore_geometry()
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

    def show_error(self, title: str, text: str) -> None:
        self.page.setHtml(status_html(title, text, spinner=False))
        self.show_window()

    def is_panel_url(self, url: QUrl) -> bool:
        return bool(self.base_url) and same_origin(url, self.base_url)

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

    def make_tray(self) -> QSystemTrayIcon | None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Открыть TG Panel", self.show_window)
        menu.addAction("Папка с данными", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.data_dir))))
        if autostart.supported():
            act = QAction("Запускать при входе в систему", menu, checkable=True)
            act.setChecked(autostart.enabled())
            act.toggled.connect(self.set_autostart)
            menu.addAction(act)
        menu.addSeparator()
        menu.addAction("Выход", self.quit)
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
