"""Где работают аккаунты: на этом компьютере (свой сервер панели внутри программы) или на вашем сервере —
тогда программа просто открывает веб-панель, и аккаунты, папки и обновления панели общие для всех устройств."""
import json
import urllib.error
import urllib.request

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QDialog, QDialogButtonBox, QLabel, QLineEdit,
                             QRadioButton, QVBoxLayout)

from paths import APP_NAME

LOCAL, REMOTE = "local", "remote"


def normalize_url(text: str) -> str:
    """'192.168.1.10/accounts' → 'http://192.168.1.10/accounts/': адреса панели относительные,
    без слэша в конце api/... ушли бы мимо её пути."""
    url = text.strip()
    if url and "://" not in url:
        url = "http://" + url
    return url if url.endswith("/") else url + "/"


def check_server(url: str) -> str | None:
    """None — по адресу отвечает TG Panel, иначе текст ошибки. /api/health открыт без пароля."""
    try:
        req = urllib.request.Request(url + "api/health", headers={"User-Agent": "TG-Panel-Desktop"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        return f"сервер ответил {e.code} — проверьте путь панели (например, /accounts/)"
    except (urllib.error.URLError, OSError) as e:
        return f"нет связи: {getattr(e, 'reason', e)}"
    except ValueError:
        return "по этому адресу не TG Panel"
    return None if "version" in data else "по этому адресу не TG Panel"


class ConnectionDialog(QDialog):
    def __init__(self, mode: str = LOCAL, url: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — подключение")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        title = QLabel("<b>Где работают ваши Telegram-аккаунты?</b>")
        layout.addWidget(title)

        self.local = QRadioButton("На этом компьютере")
        self.remote = QRadioButton("На моём сервере с TG Panel")
        group = QButtonGroup(self)
        group.addButton(self.local)
        group.addButton(self.remote)
        layout.addWidget(self.local)
        layout.addWidget(self._hint("Аккаунты подключаются прямо из программы. Сообщения приходят, пока "
                                    "программа запущена."))
        layout.addWidget(self.remote)
        layout.addWidget(self._hint("Программа открывает вашу веб-панель: аккаунты, папки и любые изменения "
                                    "панели — одни и те же на всех устройствах."))
        self.url = QLineEdit(url)
        self.url.setPlaceholderText("Адрес панели, например http://192.168.1.10/accounts/")
        layout.addWidget(self.url)
        self.error = QLabel()
        self.error.setStyleSheet("color: #e5484d")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Продолжить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        (self.remote if mode == REMOTE else self.local).setChecked(True)
        self.local.toggled.connect(self.sync)
        self.sync()

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setContentsMargins(24, 0, 0, 6)
        label.setStyleSheet("color: palette(mid)")
        return label

    def sync(self) -> None:
        self.url.setEnabled(self.remote.isChecked())
        if self.remote.isChecked():
            self.url.setFocus()
        self.error.clear()

    def on_accept(self) -> None:
        if self.local.isChecked():
            self.accept()
            return
        url = normalize_url(self.url.text())
        if url == "/":
            self.error.setText("Укажите адрес панели")
            return
        self.error.setText("Проверяем…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            problem = check_server(url)
        finally:
            QApplication.restoreOverrideCursor()
        if problem:
            self.error.setText(f"{url}: {problem}")
            return
        self.url.setText(url)
        self.accept()

    def result_value(self) -> tuple[str, str]:
        return (LOCAL, "") if self.local.isChecked() else (REMOTE, normalize_url(self.url.text()))
