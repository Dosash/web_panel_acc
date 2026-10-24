"""Новая версия панели: последний релиз на GitHub (проверка раз в 6 часов, результат — в памяти) и обновление
панели на сервере по кнопке."""
import asyncio
import http.client
import json
import logging
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .config import BASE_DIR, SELF_UPDATE, UPDATE_CHECK, UPDATE_URL, VERSION

log = logging.getLogger("panel.update")

CHECK_EVERY = 6 * 3600
RETRY_AFTER = 15 * 60   # GitHub не ответил — спросим раньше
FORCE_EVERY = 60        # «Проверить снова» не чаще раза в минуту: у GitHub лимит 60 запросов в час
# в контейнере панель обновляется пересборкой образа, без него — git pull в папке панели
DOCKER = Path("/.dockerenv").exists()

_state: dict = {"at": 0.0, "release": None, "error": ""}
_lock = asyncio.Lock()


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def _ssl_context() -> ssl.SSLContext:
    # в программе под macOS у Python нет системных корневых сертификатов — берём из certifi
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch() -> dict:
    req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": f"TG-Panel/{VERSION}",
                                                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as r:
        data = json.load(r)
    return {"latest": (data.get("tag_name") or "").lstrip("v"), "notes": (data.get("body") or "").strip()[:20000],
            "page": data.get("html_url") or "", "published_at": data.get("published_at") or ""}


async def status(force: bool = False) -> dict:
    base = {"current": VERSION, "enabled": UPDATE_CHECK, "docker": DOCKER, "self_update": mode()}
    if not UPDATE_CHECK:
        return base | {"available": False}
    async with _lock:
        age = time.time() - _state["at"]
        if age > (CHECK_EVERY if _state["release"] else RETRY_AFTER) or (force and age > FORCE_EVERY):
            try:
                _state["release"], _state["error"] = await asyncio.to_thread(_fetch), ""
            except Exception as e:  # сеть, GitHub, лимит запросов — панель работает и без проверки
                log.warning("Не удалось проверить обновления: %s", e)
                _state["error"] = str(e)
            _state["at"] = time.time()
    rel = _state["release"] or {}
    latest = rel.get("latest", "")
    return base | rel | {"available": bool(latest) and parse_version(latest) > parse_version(VERSION),
                         "checked_at": int(_state["at"]), "error": _state["error"]}


# ---------- обновление панели кнопкой ----------
# Docker: контейнер панели не может пересобрать сам себя — compose пересоздаёт его посреди команды. Поэтому
# через сокет Docker панель запускает рядом контейнер-помощник (образ docker:cli) с папкой панели на хосте,
# и уже он делает то же, что команда из README: git pull и docker compose up -d --build.
# Без Docker (run.sh, systemd): git pull и pip install в папке панели, затем перезапуск процесса.
SOCK = "/var/run/docker.sock"
HELPER_IMAGE = ("docker", "27-cli")   # в образе docker:cli есть плагин compose; git ставится при запуске
LOG_MAX = 20000
# git — от владельца папки: иначе файлы станут root-овыми и ручной git pull потом не пройдёт
HELPER_SCRIPT = """set -e
cd "$DIR"
apk add --no-cache -q git su-exec
echo "== git pull"
HOME=/tmp su-exec "$(stat -c %u:%g .git)" git pull --ff-only
echo "== docker compose up -d --build"
docker compose -p "$PROJECT" "$@" up -d --build
"""

# app/__main__.py ставит сюда функцию перезапуска процесса; без неё (программа для компьютера) — только команда
restart = None
_job: dict = {"running": False, "log": "", "error": ""}
_tasks: set = set()
_compose_info: dict = {}


class UpdateError(Exception):
    pass


def mode() -> str:
    """Как панель обновится по кнопке: docker, git или '' — никак (тогда в окне только команда)."""
    if not SELF_UPDATE:
        return ""
    if DOCKER:
        return "docker" if Path(SOCK).exists() else ""
    return "git" if restart and (BASE_DIR / ".git").exists() and shutil.which("git") else ""


async def install() -> dict:
    """Запустить обновление в фоне (скачивание образа помощника или pip могут идти минуты); ход — progress()."""
    m = mode()
    if not m:
        raise UpdateError("Здесь панель кнопкой не обновить — выполните команду из окна на сервере")
    if _job["running"]:
        raise UpdateError("Обновление уже идёт")
    _job.update(running=True, log="", error="")
    task = asyncio.create_task(asyncio.to_thread(_run_git if m == "git" else _run_docker))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    log.info("Обновление панели запущено (%s)", m)
    return {"ok": True, "mode": m}


async def progress() -> dict:
    """Ход обновления. Панель перезапустится с новой версией — `current` сменится."""
    base = {"current": VERSION, "mode": mode()}
    # без Docker всё обновление — здесь; в Docker здесь только запуск помощника, дальше — его состояние
    if _job["running"] or _job["error"] or base["mode"] == "git":
        state = "running" if _job["running"] else "failed" if _job["error"] else "done" if _job["log"] else "idle"
        return base | {"state": state, "log": _job["log"][-LOG_MAX:], "error": _job["error"]}
    if base["mode"] == "docker":
        try:
            return base | await asyncio.to_thread(_helper_state)
        except Exception as e:
            return base | {"state": "failed", "log": "", "error": f"Docker: {e}"}
    return base | {"state": "idle", "log": "", "error": ""}


# --- без Docker ---

def _sh(title: str, *cmd: str) -> None:
    _job["log"] += f"== {title}\n"
    r = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, errors="replace", timeout=900)
    _job["log"] = (_job["log"] + r.stdout + r.stderr)[-LOG_MAX:]
    if r.returncode:
        raise UpdateError(f"{title}: код выхода {r.returncode}")


def _run_git() -> None:
    try:
        _sh("git pull", "git", "pull", "--ff-only")
        _sh("pip install", sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt")
        _job["log"] += "== перезапуск панели\n"
        restart()
    except Exception as e:
        log.warning("Обновление панели не удалось: %s", e)
        _job["error"] = str(e)
    finally:
        _job["running"] = False


# --- Docker: HTTP API через unix-сокет ---

class _DockerConnection(http.client.HTTPConnection):
    def __init__(self, timeout: float):
        super().__init__("localhost", timeout=timeout)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCK)


def _docker(method: str, path: str, body: dict | None = None, timeout: float = 30) -> tuple[int, bytes]:
    conn = _DockerConnection(timeout)
    try:
        if body is None:
            conn.request(method, path)
        else:
            conn.request(method, path, json.dumps(body), {"Content-Type": "application/json"})
        r = conn.getresponse()
        return r.status, r.read()
    finally:
        conn.close()


def _docker_json(method: str, path: str, body: dict | None = None, timeout: float = 30):
    status, data = _docker(method, path, body, timeout)
    if status >= 400:
        try:
            msg = json.loads(data).get("message")
        except ValueError:
            msg = ""
        raise UpdateError(msg or f"Docker ответил {status}")
    return json.loads(data) if data.strip() else {}


def _self_id() -> str:
    """Id своего контейнера. При network_mode: host имя хоста — это имя сервера, а не id, поэтому — из точек
    монтирования (/etc/hosts и т. п. лежат в /var/lib/docker/containers/<id>/), иначе — по container_name."""
    try:
        m = re.search(r"/containers/([0-9a-f]{64})/", Path("/proc/self/mountinfo").read_text())
    except OSError:
        m = None
    return m.group(1) if m else "tg-panel"


def _compose() -> dict:
    """Проект compose, в котором запущена панель, — по меткам, которые docker compose ставит контейнеру."""
    if not _compose_info:
        labels = (_docker_json("GET", f"/containers/{_self_id()}/json").get("Config") or {}).get("Labels") or {}
        project, workdir = labels.get("com.docker.compose.project"), labels.get("com.docker.compose.project.working_dir")
        if not (project and workdir):
            raise UpdateError("Контейнер запущен не через docker compose — обновите его вручную")
        files = [f for f in (labels.get("com.docker.compose.project.config_files") or "").split(",") if f]
        _compose_info.update(project=project, dir=workdir, files=files, helper=f"{project}-updater")
    return _compose_info


def _run_docker() -> None:
    try:
        _start_helper()
    except Exception as e:  # нет доступа к сокету, Docker не ответил, образ не скачался
        log.warning("Не удалось запустить обновление: %s", e)
        _job["error"] = str(e) if isinstance(e, UpdateError) else f"Docker: {e}"
    finally:
        _job["running"] = False


def _start_helper() -> None:
    c = _compose()
    status, data = _docker("GET", f"/containers/{c['helper']}/json")
    if status == 200:
        if json.loads(data)["State"]["Running"]:
            raise UpdateError("Обновление уже идёт")
        _docker_json("DELETE", f"/containers/{c['helper']}?force=true")
    image = ":".join(HELPER_IMAGE)
    if _docker("GET", f"/images/{image}/json")[0] != 200:
        _job["log"] += f"== скачиваем образ {image}\n"
        # ответ — поток JSON-строк о ходе скачивания; ошибка приходит в нём же
        name, tag = HELPER_IMAGE
        status, data = _docker("POST", f"/images/create?fromImage={name}&tag={tag}", timeout=600)
        err = next((json.loads(x).get("error") for x in data.splitlines() if b'"error"' in x), None)
        if status >= 400 or err:
            raise UpdateError(f"Не удалось скачать образ {image}: {err or status}")
    args = [a for f in c["files"] for a in ("-f", f)]
    _docker_json("POST", f"/containers/create?name={c['helper']}", {
        "Image": image, "Cmd": ["sh", "-c", HELPER_SCRIPT, "updater", *args],
        "Env": [f"DIR={c['dir']}", f"PROJECT={c['project']}"],
        "Labels": {"tg-panel.updater": c["project"]},
        "HostConfig": {"Binds": [f"{SOCK}:{SOCK}", f"{c['dir']}:{c['dir']}"], "NetworkMode": "host"},
    })
    _docker_json("POST", f"/containers/{c['helper']}/start")


def _demux(raw: bytes) -> str:
    """Журнал контейнера без TTY: кадры с 8-байтовым заголовком (поток, 0, 0, 0, длина)."""
    out, i = [], 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        out.append(raw[i + 8:i + 8 + size])
        i += 8 + size
    return b"".join(out).decode(errors="replace")


def _helper_state() -> dict:
    c = _compose()
    status, data = _docker("GET", f"/containers/{c['helper']}/json")
    if status == 404:
        return {"state": "idle", "log": "", "error": ""}
    st = json.loads(data)["State"]
    text = _demux(_docker("GET", f"/containers/{c['helper']}/logs?stdout=1&stderr=1&tail=200")[1])[-LOG_MAX:]
    if st["Running"]:
        return {"state": "running", "log": text, "error": ""}
    if st["ExitCode"]:
        return {"state": "failed", "log": text, "error": f"Обновление прервалось (код выхода {st['ExitCode']})"}
    return {"state": "done", "log": text, "error": ""}
