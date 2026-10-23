"""Одна запущенная копия: повторный запуск только показывает окно уже работающей."""
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activated = pyqtSignal()  # другая копия попросила показать окно

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.server: QLocalServer | None = None

    def forward_to_running(self) -> bool:
        """True — копия уже запущена (ей отправлено «show»), этой нужно выйти."""
        for _ in range(3):
            if self._send_show():
                return True
            # никто не ответил — сокет мог остаться от упавшей копии
            QLocalServer.removeServer(self.name)
            server = QLocalServer(self)
            server.setSocketOptions(QLocalServer.UserAccessOption)
            if server.listen(self.name):
                self.server = server
                server.newConnection.connect(self._on_connection)
                return False
            # две копии запустились одновременно и вторая заняла имя первой — спросим её ещё раз
            server.deleteLater()
            QThread.msleep(200)
        raise RuntimeError(f"Не удалось проверить, запущена ли уже программа: {self.name}")

    def _send_show(self) -> bool:
        sock = QLocalSocket()
        sock.connectToServer(self.name)
        if not sock.waitForConnected(500):
            return False
        sock.write(b"show")
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return True

    def _on_connection(self) -> None:
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            conn.readyRead.connect(conn.readAll)
            conn.disconnected.connect(conn.deleteLater)
            self.activated.emit()

    def close(self) -> None:
        if self.server:
            self.server.close()
