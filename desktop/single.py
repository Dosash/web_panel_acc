"""Одна запущенная копия: повторный запуск только показывает окно уже работающей."""
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activated = pyqtSignal()  # другая копия попросила показать окно

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.server: QLocalServer | None = None

    def forward_to_running(self) -> bool:
        """True — копия уже запущена (ей отправлено «show»), этой нужно выйти."""
        sock = QLocalSocket()
        sock.connectToServer(self.name)
        if sock.waitForConnected(500):
            sock.write(b"show")
            sock.waitForBytesWritten(500)
            sock.disconnectFromServer()
            return True
        # никто не ответил — сокет мог остаться от упавшей копии
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self._on_connection)
        self.server.listen(self.name)
        return False

    def _on_connection(self) -> None:
        while self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            conn.readyRead.connect(conn.readAll)
            conn.disconnected.connect(conn.deleteLater)
            self.activated.emit()

    def close(self) -> None:
        if self.server:
            self.server.close()
