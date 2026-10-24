# PyInstaller: серверная часть TG Panel для Windows — tg-panel-server.exe (onedir, без окна).
# Запускать через desktop-win/build.ps1 (он готовит значок и сведения о версии в desktop-win/build/).
# Qt здесь только ради opentele (чтение tdata): из PyQt5 берём QtCore, без WebEngine, Widgets и Gui.
import re
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = Path(SPECPATH)
ROOT = HERE.parents[1]
BUILD = HERE.parent / "build"

a = Analysis(
    [str(HERE / "main.py")],
    pathex=[str(ROOT)],
    # static/ рядом с app/: app.config берёт BASE_DIR как папку над app/ — в сборке это корень распаковки
    datas=[(str(ROOT / "static"), "static"),
           # веб-панели встроенных ботов (bots/): их static ищется рядом с модулем
           (str(ROOT / "bots" / "posts" / "web" / "static"), "bots/posts/web/static"),
           (str(ROOT / "bots" / "ads" / "web_static"), "bots/ads/web_static")]
    + collect_data_files("tzdata"),
    # uvicorn и Telethon подгружают модули по имени — анализ импортов их не видит (как desktop/tg-panel.spec)
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("app") + collect_submodules("telethon")
    + collect_submodules("opentele") + collect_submodules("bots") + collect_submodules("aiogram")
    + ["aiosqlite", "PyQt5.QtCore"],
    # PIL Telethon использует, только если он установлен; watchfiles — перезапуск uvicorn при правках
    excludes=["tkinter", "PIL", "watchfiles", "PyQt5.QtGui", "PyQt5.QtWidgets", "PyQt5.QtNetwork", "PyQt5.QtSvg",
              "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngineCore", "PyQt5.QtWebEngine", "PyQt5.QtQml",
              "PyQt5.QtQuick", "PyQt5.QtWebChannel", "PyQt5.QtPrintSupport", "PyQt5.QtDBus"],
    noarchive=False,
)

# из Qt нужны только Qt5Core.dll и QtCore.pyd: плагины, переводы, qml, OpenGL/ANGLE и прочие модули — мимо
QT_DLL = re.compile(r"[/\\]Qt5?[/\\]bin[/\\]", re.I)
QT_KEEP = re.compile(r"Qt5Core\.dll$", re.I)
QT_DROP = re.compile(r"[/\\]Qt5?[/\\](plugins|translations|qml|resources)[/\\]|opengl32sw|d3dcompiler|libEGL|libGLESv2",
                     re.I)


def needed(entry) -> bool:
    dest = "/" + entry[0]
    if QT_DROP.search(dest):
        return False
    return not QT_DLL.search(dest) or bool(QT_KEEP.search(dest))


a.binaries = [e for e in a.binaries if needed(e)]
a.datas = [e for e in a.datas if needed(e)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tg-panel-server",
    console=False,  # без окна консоли: stdin/stdout — каналы оболочки (main.open_std_streams)
    icon=str(BUILD / "icon.ico"),
    version=str(BUILD / "server_version_info.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="tg-panel-server", upx=False)
