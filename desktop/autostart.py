"""Запуск при входе в систему: ярлык в автозагрузке (Linux), ключ Run в реестре (Windows),
LaunchAgent (macOS). Приложение стартует свёрнутым в трей (--hidden)."""
import plistlib
import shlex
import sys
from pathlib import Path

from paths import APP_ID, APP_NAME, FROZEN, executable

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MAC_LABEL = "io.github.dosash.tgpanel"


def supported() -> bool:
    # из исходников автозапуск бы ссылался на временное окружение разработчика
    return FROZEN and sys.platform in ("win32", "darwin", "linux")


def _command() -> list[str]:
    return executable() + ["--hidden"]


def _linux_file() -> Path:
    import os
    base = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / f"{APP_ID}.desktop"


def _mac_file() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return _mac_file().exists()
    return _linux_file().exists()


def set_enabled(on: bool) -> None:
    cmd = _command()
    if sys.platform == "win32":
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return
    path = _mac_file() if sys.platform == "darwin" else _linux_file()
    if not on:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        path.write_bytes(plistlib.dumps({"Label": MAC_LABEL, "ProgramArguments": cmd, "RunAtLoad": True}))
    else:
        path.write_text("[Desktop Entry]\nType=Application\n"
                        f"Name={APP_NAME}\nExec={shlex.join(cmd)}\nIcon={APP_ID}\n"
                        "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
