# PyInstaller: сборка десктоп-приложения под текущую ОС. Запускать через build.py (он готовит значки).
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

HERE = Path(SPECPATH)
ROOT = HERE.parent
ICONS = HERE / "build" / "icons"
VERSION = re.search(r'^VERSION = "([^"]+)"', (ROOT / "app" / "config.py").read_text("utf-8"), re.M).group(1)
NAME = "tg-panel" if sys.platform.startswith("linux") else "TG Panel"

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(ROOT), str(HERE)],
    # static/ рядом с app/: app.config берёт BASE_DIR как папку над app/ — в сборке это корень распаковки
    datas=[(str(ROOT / "static"), "static"), (str(HERE / "icon.svg"), "."),
           (str(HERE / "build" / "version.txt"), ".")],
    # uvicorn и Telethon подгружают модули по имени — анализ импортов их не видит
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("app") + collect_submodules("telethon")
    + collect_submodules("opentele") + ["PyQt5.QtSvg", "PyQt5.QtNetwork"],
    # PIL Telethon использует, только если он установлен; watchfiles — перезапуск uvicorn при правках
    excludes=["tkinter", "PIL", "watchfiles"],
    noarchive=False,
)

# Хуки PyQt5 кладут весь Qt; встроенному браузеру нужны Core/Gui/Widgets/Network/Svg/Qml/Quick/WebChannel/
# Positioning/PrintSupport и сам WebEngine. Остальное (3D, Bluetooth, мультимедиа, QML-модули) — ~100 МБ лишнего
UNUSED_QT = re.compile(
    r"Qt5?(Bluetooth|Location|Multimedia\w*|Nfc|PositioningQuick|Quick3D\w*|QuickControls2|QuickParticles|"
    r"QuickShapes|QuickTemplates2|QuickTest|RemoteObjects|Sensors|SerialPort|Sql|Test|WebView|XmlPatterns|"
    r"WebEngine|Designer|Help|TextToSpeech|Gamepad|Scxml|WebSockets|Concurrent)\b"
    r"|qwebgl|serialnmea|[/\\]Qt5?[/\\]qml[/\\]")
# переводы Qt и Chromium — только русский и английский
TRANSLATION = re.compile(r"[/\\]translations[/\\]")
KEEP_TRANSLATION = re.compile(r"(_ru|_en)\.qm$|[/\\](ru|en-US)\.pak$")


def needed(entry) -> bool:
    dest = "/" + entry[0]
    if UNUSED_QT.search(dest):
        return False
    return not TRANSLATION.search(dest) or bool(KEEP_TRANSLATION.search(dest))


a.binaries = [e for e in a.binaries if needed(e)]
a.datas = [e for e in a.datas if needed(e)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,  # без окна консоли под Windows
    # под Linux значок у файла не задать — он в .desktop-ярлыке и AppImage
    icon={"win32": str(ICONS / "icon.ico"), "darwin": str(ICONS / "icon.icns")}.get(sys.platform),
    version=str(HERE / "build" / "version_info.txt") if sys.platform == "win32" else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="TG Panel.app",
        icon=str(ICONS / "icon.icns"),
        bundle_identifier="io.github.dosash.tgpanel",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "TG Panel",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSApplicationCategoryType": "public.app-category.social-networking",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSCameraUsageDescription": "Мини-приложения ботов могут попросить доступ к камере.",
            "NSMicrophoneUsageDescription": "Мини-приложения ботов могут попросить доступ к микрофону.",
        },
    )
