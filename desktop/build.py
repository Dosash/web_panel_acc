"""Сборка десктоп-приложения под текущую ОС.

    python desktop/build.py

Нужен Python 3.12 с пакетами из desktop/requirements.txt. Результат — в desktop/release/:
  Linux    TG-Panel-<версия>-linux-x86_64.tar.gz (+ .AppImage, если найден appimagetool)
  Windows  TG-Panel-<версия>-windows-x64-setup.exe (если установлен Inno Setup 6) и -portable.zip
  macOS    TG-Panel-<версия>-macos-<arm64|x86_64>.dmg
Собрать программу под другую ОС отсюда нельзя — для этого GitHub Actions (.github/workflows/desktop.yml)."""
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
ICONS = BUILD / "icons"
DIST = HERE / "dist"
RELEASE = HERE / "release"
VERSION = re.search(r'^VERSION = "([^"]+)"', (ROOT / "app" / "config.py").read_text("utf-8"), re.M).group(1)
ARCH = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(
    platform.machine().lower(), platform.machine().lower())


def step(text: str) -> None:
    print(f"\n==> {text}", flush=True)


def make_icons() -> None:
    """icon.svg → PNG нужных размеров (через QtSvg), из них .ico и .icns (Pillow)."""
    from PIL import Image
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QGuiApplication, QImage, QPainter
    from PyQt5.QtSvg import QSvgRenderer

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 — QPainter нужен QGuiApplication
    ICONS.mkdir(parents=True, exist_ok=True)
    renderer = QSvgRenderer(str(HERE / "icon.svg"))
    pngs = {}
    for size in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p)
        p.end()
        path = ICONS / f"icon_{size}.png"
        img.save(str(path))
        pngs[size] = path
    shutil.copy(pngs[512], ICONS / "icon.png")
    big = Image.open(pngs[1024])
    big.save(ICONS / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    if sys.platform == "darwin":
        big.save(ICONS / "icon.icns")


def windows_version_info() -> None:
    nums = (tuple(int(x) for x in re.findall(r"\d+", VERSION)[:3]) + (0, 0, 0, 0))[:4]
    (BUILD / "version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041904B0', [
      StringStruct('CompanyName', 'TG Panel'),
      StringStruct('FileDescription', 'TG Panel — Telegram-аккаунты в одном окне'),
      StringStruct('FileVersion', '{VERSION}'),
      StringStruct('InternalName', 'TG Panel'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'TG Panel.exe'),
      StringStruct('ProductName', 'TG Panel'),
      StringStruct('ProductVersion', '{VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [1049, 1200])])
  ]
)
""", encoding="utf-8")


def pyinstaller() -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", str(HERE / "tg-panel.spec"), "--noconfirm", "--clean",
                    "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller")], check=True, cwd=HERE)


def tar_dir(src: Path, out: Path, arcname: str) -> None:
    def keep_mode(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        return info
    with tarfile.open(out, "w:gz", compresslevel=6) as tar:
        tar.add(src, arcname=arcname, filter=keep_mode)


def package_linux() -> None:
    app_dir = DIST / "tg-panel"
    linux = HERE / "packaging" / "linux"
    shutil.copy(ICONS / "icon.png", app_dir / "tg-panel.png")
    shutil.copy(linux / "tg-panel.desktop", app_dir / "tg-panel.desktop")
    shutil.copy(linux / "install.sh", app_dir / "install.sh")
    (app_dir / "install.sh").chmod(0o755)
    out = RELEASE / f"TG-Panel-{VERSION}-linux-{ARCH}.tar.gz"
    step(f"Архив {out.name}")
    tar_dir(app_dir, out, "tg-panel")

    tool = os.getenv("APPIMAGETOOL") or shutil.which("appimagetool")
    if not tool:
        print("appimagetool не найден — AppImage пропущен (укажите путь в APPIMAGETOOL)")
        return
    step("AppImage")
    appdir = BUILD / "AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    shutil.copytree(app_dir, appdir / "usr" / "lib" / "tg-panel", symlinks=True)
    shutil.copy(linux / "AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    shutil.copy(linux / "tg-panel.desktop", appdir / "tg-panel.desktop")
    shutil.copy(ICONS / "icon.png", appdir / "tg-panel.png")
    shutil.copy(ICONS / "icon.png", appdir / ".DirIcon")
    out = RELEASE / f"TG-Panel-{VERSION}-linux-{ARCH}.AppImage"
    env = dict(os.environ, ARCH=ARCH if ARCH != "arm64" else "aarch64", APPIMAGE_EXTRACT_AND_RUN="1")
    subprocess.run([tool, "--no-appstream", str(appdir), str(out)], check=True, env=env)


def find_iscc() -> str | None:
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    for base in (os.getenv("ProgramFiles(x86)"), os.getenv("ProgramFiles"), os.getenv("LOCALAPPDATA")):
        if base:
            for sub in ("Inno Setup 6", r"Programs\Inno Setup 6"):
                path = Path(base) / sub / "ISCC.exe"
                if path.exists():
                    return str(path)
    return None


def package_windows() -> None:
    app_dir = DIST / "TG Panel"
    out = RELEASE / f"TG-Panel-{VERSION}-windows-x64-portable.zip"
    step(f"Архив {out.name}")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in app_dir.rglob("*"):
            z.write(path, Path("TG Panel") / path.relative_to(app_dir))
        # с этим файлом данные хранятся рядом с программой (флешка), а не в %APPDATA%
        z.writestr("TG Panel/portable.txt", "Данные TG Panel хранятся в папке data рядом с программой.\n"
                                            "Удалите этот файл, чтобы хранить их в %APPDATA%\\TG Panel.\n")
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup 6 не найден — установщик пропущен (https://jrsoftware.org/isdl.php)")
        return
    step("Установщик Inno Setup")
    subprocess.run([iscc, f"/DAppVersion={VERSION}", f"/DSourceDir={app_dir}", f"/DOutputDir={RELEASE}",
                    f"/DIconFile={ICONS / 'icon.ico'}", f"/DOutputName=TG-Panel-{VERSION}-windows-x64-setup",
                    str(HERE / "packaging" / "windows" / "installer.iss")], check=True)


def package_macos() -> None:
    app = DIST / "TG Panel.app"
    # подпись «ad-hoc»: без неё Apple Silicon не запустит программу вовсе
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
    stage = BUILD / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    subprocess.run(["ditto", str(app), str(stage / "TG Panel.app")], check=True)
    (stage / "Applications").symlink_to("/Applications")
    out = RELEASE / f"TG-Panel-{VERSION}-macos-{ARCH}.dmg"
    step(f"Образ {out.name}")
    # на раннерах GitHub hdiutil иногда падает с «Resource busy» (образ ещё проверяет XProtect) — повторяем
    for attempt in range(1, 6):
        out.unlink(missing_ok=True)
        result = subprocess.run(["hdiutil", "create", "-volname", "TG Panel", "-srcfolder", str(stage), "-ov",
                                 "-format", "UDZO", str(out)])
        if result.returncode == 0:
            break
        if attempt == 5:
            raise subprocess.CalledProcessError(result.returncode, result.args)
        print(f"hdiutil не удался, повтор {attempt + 1}/5 через {attempt * 5} с", flush=True)
        time.sleep(attempt * 5)


def main() -> None:
    # консоль Windows (и вывод в GitHub Actions) по умолчанию не в UTF-8 — русский текст уронил бы print
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"TG Panel {VERSION}, {sys.platform}/{ARCH}, Python {platform.python_version()}")
    if sys.version_info[:2] != (3, 12):
        print("Внимание: проект проверен на Python 3.12")
    for d in (DIST, BUILD / "pyinstaller"):
        shutil.rmtree(d, ignore_errors=True)
    RELEASE.mkdir(parents=True, exist_ok=True)
    step("Значки")
    make_icons()
    (BUILD / "version.txt").write_text(VERSION, encoding="utf-8")  # версия для обновлений (paths.version)
    if sys.platform == "win32":
        windows_version_info()
    step("PyInstaller")
    pyinstaller()
    if sys.platform == "win32":
        package_windows()
    elif sys.platform == "darwin":
        package_macos()
    else:
        package_linux()
    step("Готово")
    for f in sorted(RELEASE.iterdir()):
        if VERSION in f.name:
            print(f"  {f}  ({f.stat().st_size / 1e6:.0f} МБ)")


if __name__ == "__main__":
    main()
