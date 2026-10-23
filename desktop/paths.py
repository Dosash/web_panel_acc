"""Где приложение держит данные и откуда берёт свои файлы — и в сборке PyInstaller, и при запуске из исходников."""
import os
import sys
from pathlib import Path

APP_NAME = "TG Panel"
APP_ID = "tg-panel"
FROZEN = getattr(sys, "frozen", False)


def data_dir() -> Path:
    """База, ключ шифрования сессий, кэш, профиль встроенного браузера, журнал.
    Не в папке программы: обновление или переустановка не трогают аккаунты."""
    custom = os.getenv("TG_PANEL_DATA", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    if FROZEN:
        # переносная версия (zip для Windows): данные рядом с программой
        here = Path(sys.executable).resolve().parent
        if (here / "portable.txt").exists():
            return here / "data"
    if sys.platform == "win32":
        return Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_ID


def resource(name: str) -> Path:
    """Файл, который едет вместе с программой (значок)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def executable() -> list[str]:
    """Команда запуска этой копии программы — для автозапуска при входе в систему."""
    if os.getenv("APPIMAGE"):  # внутри AppImage sys.executable указывает во временную точку монтирования
        return [os.environ["APPIMAGE"]]
    if FROZEN:
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve().parent / "launcher.py")]


def version() -> str:
    """Версия программы: в сборке — файл version.txt (build.py), из исходников — VERSION в app/config.py.
    app.config не импортируем: он создаёт ключи в папке данных, а в режиме сервера они не нужны."""
    import re
    bundled = resource("version.txt")
    if FROZEN and bundled.exists():
        return bundled.read_text("utf-8").strip()
    config = Path(__file__).resolve().parent.parent / "app" / "config.py"
    return re.search(r'^VERSION = "([^"]+)"', config.read_text("utf-8"), re.M).group(1)


def clean_env() -> dict[str, str]:
    """Окружение для внешних программ (notify-send, скрипт обновления): без путей к библиотекам сборки —
    PyInstaller под Linux подставляет свои в LD_LIBRARY_PATH, и системные программы с ними падают."""
    env = dict(os.environ)
    for var in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        orig = env.pop(var + "_ORIG", None)
        if orig is not None:
            env[var] = orig
        elif FROZEN:
            env.pop(var, None)
    for var in ("WEB_PASSWORD", "QTWEBENGINE_REMOTE_DEBUGGING"):  # новой копии свои
        env.pop(var, None)
    return env
