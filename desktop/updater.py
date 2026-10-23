"""Обновление программы из GitHub Releases: проверка, загрузка файла под эту систему и установка
после выхода (скрипт ждёт, пока программа закроется, ставит новую версию и запускает её снова).

Как установлена программа → чем обновляется:
  Windows установщик  → новый setup.exe в тихом режиме (папка и ярлыки прежние)
  Windows portable    → файлы из zip поверх папки программы (data/ не трогается)
  Linux AppImage      → новый .AppImage на месте старого
  Linux tar.gz        → новая папка на месте старой (после install.sh — в ~/.local/opt/tg-panel)
  macOS               → TG Panel.app из нового .dmg на место старого
Из исходников программа только сообщает о новой версии."""
import json
import logging
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from paths import FROZEN, clean_env, executable

log = logging.getLogger("desktop.update")

REPO = "Dosash/web_panel_acc"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
# адрес можно подменить — для проверки обновления на своём сервере
API_URL = os.getenv("TG_PANEL_UPDATE_URL") or f"https://api.github.com/repos/{REPO}/releases/latest"
ARCH = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(
    platform.machine().lower(), platform.machine().lower())


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def install_kind() -> str | None:
    if not FROZEN:
        return None
    if sys.platform == "win32":
        return "portable" if (Path(sys.executable).parent / "portable.txt").exists() else "setup"
    if sys.platform == "darwin":
        return "dmg"
    return "appimage" if os.getenv("APPIMAGE") else "tar"


ASSET_SUFFIX = {
    "setup": "-windows-x64-setup.exe",
    "portable": "-windows-x64-portable.zip",
    "dmg": f"-macos-{ARCH}.dmg",
    "appimage": f"-linux-{ARCH}.AppImage",
    "tar": f"-linux-{ARCH}.tar.gz",
}


@dataclass
class Release:
    version: str
    notes: str
    page: str
    asset_url: str = ""
    asset_name: str = ""


def _ssl_context() -> ssl.SSLContext:
    # в сборке под macOS у Python нет системных корневых сертификатов — берём из certifi
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _open(url: str, timeout: float = 20):
    req = urllib.request.Request(url, headers={"User-Agent": "TG-Panel-Desktop", "Accept": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def fetch_latest() -> Release:
    with _open(API_URL) as r:
        data = json.load(r)
    rel = Release(version=data.get("tag_name", "").lstrip("v"), notes=(data.get("body") or "").strip(),
                  page=data.get("html_url") or RELEASES_PAGE)
    kind = install_kind()
    suffix = ASSET_SUFFIX.get(kind or "")
    for asset in data.get("assets", []):
        if suffix and asset.get("name", "").endswith(suffix):
            rel.asset_url, rel.asset_name = asset["browser_download_url"], asset["name"]
    return rel


def _q(s: str | Path) -> str:
    """Строка в одинарных кавычках для sh."""
    return "'" + str(s).replace("'", "'\"'\"'") + "'"


def _ps(s: str | Path) -> str:
    """Строка в одинарных кавычках для PowerShell."""
    return "'" + str(s).replace("'", "''") + "'"


class Installer:
    """Готовит обновление, пока программа работает, и запускает скрипт, который закончит его после выхода."""

    def __init__(self, kind: str, file: Path, work: Path):
        self.kind, self.file, self.work = kind, file, work
        self.version = ""
        self.commands: list[str] = []  # шаги скрипта после выхода программы
        self.start: list[str] = executable()

    def prepare(self) -> None:
        getattr(self, "_prepare_" + self.kind)()

    def _prepare_appimage(self) -> None:
        target = Path(os.environ["APPIMAGE"])
        new = target.with_name(f".{target.name}.new")  # рядом — тогда замена атомарная
        shutil.copyfile(self.file, new)
        new.chmod(0o755)
        self.commands = [f"mv -f {_q(new)} {_q(target)}"]

    def _prepare_tar(self) -> None:
        app_dir = Path(sys.executable).resolve().parent
        stage = app_dir.parent / f".{app_dir.name}.update"
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir()
        with tarfile.open(self.file) as tar:
            tar.extractall(stage, filter="data")
        new = stage / "tg-panel"
        self.commands = [f"rm -rf {_q(app_dir)}", f"mv {_q(new)} {_q(app_dir)}", f"rm -rf {_q(stage)}"]
        self.start = [str(app_dir / "tg-panel")]

    def _prepare_dmg(self) -> None:
        app = Path(sys.executable).resolve().parents[2]  # …/TG Panel.app/Contents/MacOS/TG Panel
        mnt = self.work / "mnt"
        mnt.mkdir(exist_ok=True)
        subprocess.run(["hdiutil", "attach", str(self.file), "-nobrowse", "-readonly", "-mountpoint", str(mnt)],
                       check=True, capture_output=True, env=clean_env())
        try:
            stage = app.parent / f".{app.name}.update"
            shutil.rmtree(stage, ignore_errors=True)
            subprocess.run(["ditto", str(mnt / "TG Panel.app"), str(stage)], check=True, env=clean_env())
        finally:
            subprocess.run(["hdiutil", "detach", str(mnt), "-quiet"], env=clean_env())
        self.commands = [f"rm -rf {_q(app)}", f"mv {_q(stage)} {_q(app)}", f"xattr -cr {_q(app)} || true"]
        self.start = ["open", str(app)]

    def _prepare_setup(self) -> None:
        # тихая установка в ту же папку (Inno Setup помнит её по AppId), с окном прогресса
        self.commands = [f"Start-Process -FilePath {_ps(self.file)} -Wait "
                         "-ArgumentList '/SILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOCANCEL'"]

    def _prepare_portable(self) -> None:
        app_dir = Path(sys.executable).resolve().parent
        stage = self.work / "unzip"
        with zipfile.ZipFile(self.file) as z:
            z.extractall(stage)
        new = stage / "TG Panel"
        self.commands = [f"Remove-Item -LiteralPath {_ps(app_dir / '_internal')} -Recurse -Force "
                         "-ErrorAction SilentlyContinue",
                         f"Copy-Item -Path {_ps(str(new) + '/*')} -Destination {_ps(app_dir)} -Recurse -Force"]

    def launch(self, relaunch: bool, args: list[str]) -> None:
        start = self.start + (["--args"] if self.start[0] == "open" and args else []) + args  # macOS: open … --args
        launch_after_exit(self.commands, start if relaunch else None, self.work)


def launch_after_exit(commands: list[str], start: list[str] | None, work: Path) -> None:
    """Скрипт, который дождётся выхода этой программы, выполнит commands и запустит start."""
    pid = os.getpid()
    work.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        lines = [f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue", *commands]
        if start:
            rest = ",".join(_ps(a) for a in start[1:])
            lines.append(f"Start-Process -FilePath {_ps(start[0])}" + (f" -ArgumentList {rest}" if rest else ""))
        script = work / "update.ps1"
        script.write_text("\r\n".join(lines), encoding="utf-8-sig")
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)]
        # не DETACHED_PROCESS: без консоли PowerShell 5.1 молча выходит с кодом 0, не выполнив скрипт.
        # CREATE_NO_WINDOW — своя скрытая консоль, и процесс переживает выход программы
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        try:
            # программа работает в задании Windows (Job Object) — на случай, если оно завершает дочерние
            # процессы вместе с программой, выводим скрипт из задания
            subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, close_fds=True,
                             env=clean_env())
        except OSError:  # задание запрещает выход из него
            subprocess.Popen(cmd, creationflags=flags, close_fds=True, env=clean_env())
    else:
        lines = [f"while kill -0 {pid} 2>/dev/null; do sleep 0.5; done", "set -e", *commands, "set +e"]
        if start:
            lines.append(f"nohup {' '.join(_q(a) for a in start)} >/dev/null 2>&1 &")
        script = work / "update.sh"
        script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True, env=clean_env(),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info("Скрипт после выхода: %s", script)


def restart(args: list[str], work: Path) -> None:
    """Перезапуск программы после выхода (смена подключения)."""
    launch_after_exit([], executable() + args, work)


class Updater(QObject):
    """Проверка и загрузка в фоновом потоке, результаты — сигналами в поток окна."""
    found = pyqtSignal(object)          # Release новее текущей
    up_to_date = pyqtSignal(str)        # последняя версия — текущая
    ready = pyqtSignal(object)          # Installer: можно ставить
    failed = pyqtSignal(str)

    def __init__(self, current: str, work: Path):
        super().__init__()
        self.current = current
        self.work = work
        self.kind = install_kind()
        self.busy = False
        self.installer: Installer | None = None

    def can_install(self, rel: Release) -> bool:
        if not (self.kind and rel.asset_url):
            return False
        if self.kind == "appimage":
            return os.access(Path(os.environ["APPIMAGE"]).parent, os.W_OK)
        if self.kind in ("tar", "portable"):
            return os.access(Path(sys.executable).resolve().parent.parent, os.W_OK)
        if self.kind == "dmg":
            return os.access(Path(sys.executable).resolve().parents[3], os.W_OK)
        return True

    def check(self, download: bool) -> None:
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._check, args=(download,), name="update-check", daemon=True).start()

    def _check(self, download: bool) -> None:
        try:
            rel = fetch_latest()
            if not rel.version or parse_version(rel.version) <= parse_version(self.current):
                self.up_to_date.emit(rel.version or self.current)
                return
            log.info("Доступна версия %s (сейчас %s)", rel.version, self.current)
            self.found.emit(rel)
            if download and self.can_install(rel):
                self.ready.emit(self._download(rel))
        except Exception as e:  # сеть, GitHub, диск — обновление не должно ронять программу
            log.warning("Обновление не удалось: %s", e)
            self.failed.emit(str(e))
        finally:
            self.busy = False

    def _download(self, rel: Release) -> Installer:
        work = self.work / rel.version
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        file = work / rel.asset_name
        with _open(rel.asset_url, timeout=60) as r, open(file, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        log.info("Скачано: %s (%.0f МБ)", file, file.stat().st_size / 1e6)
        installer = Installer(self.kind, file, Path(tempfile.mkdtemp(prefix="tg-panel-update-", dir=work)))
        installer.version = rel.version
        installer.prepare()
        self.installer = installer
        return installer
