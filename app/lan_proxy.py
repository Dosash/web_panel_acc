"""Прокси веб-панели из локальной сети (LAN_PANEL_URL) на отдельном порту.

Панель запрещает встраивание (X-Frame-Options, frame-ancestors), поэтому iframe смотрит не на неё,
а на этот прокси. Прокси отдаёт её как есть и вырезает только запрет встраивания.

Почему отдельный порт, а не путь /lan/... на основном: в JS под-панелей зашиты абсолютные пути
(/api/health, /parser/assets/..., /onlik/_next/...), надёжно переписать их нельзя, а /api ещё
и пересекается с API самой TG Panel. Отдельный порт — отдельный origin, пути не трогаем.
Cookie входа в TG Panel привязана к хосту без порта, так что доступ проверяется той же cookie.
"""
import asyncio
import contextlib
import html
import logging
import socket
from urllib.parse import urlsplit

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import HTMLResponse, StreamingResponse
from starlette.routing import Route

log = logging.getLogger("panel.lan")

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade"}
# HSTS по http браузер всё равно игнорирует, но на чужом порту он ни к чему
DROP_RESPONSE = HOP | {"x-frame-options", "strict-transport-security"}
METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

PAGE = """<!doctype html><meta charset="utf-8"><meta name="color-scheme" content="light dark">
<title>{title}</title><body style="font:15px/1.5 system-ui,sans-serif;display:grid;place-items:center;min-height:90vh;margin:0">
<div style="text-align:center;max-width:420px;padding:16px"><h3>{title}</h3><p>{text}</p></div>"""


def _page(title: str, text: str, status: int) -> HTMLResponse:
    return HTMLResponse(PAGE.format(title=html.escape(title), text=html.escape(text)), status)


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _strip_frame_ancestors(csp: str) -> str:
    parts = (p.strip() for p in csp.split(";"))
    return "; ".join(p for p in parts if p and not p.lower().startswith("frame-ancestors"))


def _strip_cookie(header: str, name: str) -> str:
    # cookie панели не должна уходить на чужой сервер
    parts = (p.strip() for p in header.split(";"))
    return "; ".join(p for p in parts if p and p.split("=", 1)[0] != name)


def build_app(upstream: str, allowed, cookie_name: str) -> Starlette:
    """allowed(request) -> bool — проверка входа в TG Panel."""
    up = _origin(upstream)
    client = httpx.AsyncClient(timeout=httpx.Timeout(15, read=300), follow_redirects=False)

    async def proxy(request: Request):
        if not allowed(request):
            return _page("Нужен вход", "Войдите в TG Panel и обновите эту страницу.", 401)
        here = f"{request.url.scheme}://{request.url.netloc}"

        headers = []
        for k, v in request.headers.raw:
            name, value = k.decode("latin-1").lower(), v.decode("latin-1")
            if name in HOP or name == "host":
                continue
            if name == "cookie":
                value = _strip_cookie(value, cookie_name)
                if not value:
                    continue
            elif name in ("origin", "referer") and value.startswith(here):
                value = up + value[len(here):]
            headers.append((name, value.encode("latin-1")))

        target = (request.scope.get("raw_path") or request.url.path.encode()).decode("latin-1")
        if request.url.query:
            target += "?" + request.url.query
        has_body = "content-length" in request.headers or "transfer-encoding" in request.headers
        req = client.build_request(request.method, up + target, headers=headers,
                                   content=request.stream() if has_body else None)
        try:
            resp = await client.send(req, stream=True)
        except httpx.HTTPError as e:
            log.warning("LAN-панель %s недоступна: %r", up, e)
            return _page("Панель недоступна", f"{up} не отвечает: {type(e).__name__}", 502)

        out = []
        for k, v in resp.headers.raw:
            name, value = k.decode("latin-1").lower(), v.decode("latin-1")
            if name in DROP_RESPONSE:
                continue
            if name == "content-security-policy":
                value = _strip_frame_ancestors(value)
                if not value:
                    continue
            elif name in ("location", "content-location", "refresh"):
                # абсолютные редиректы на сам сервер → на прокси
                value = value.replace(up + "/", "/").replace(up, "/")
            elif name == "set-cookie":
                if value.split("=", 1)[0].strip() == cookie_name:
                    continue
                value = ";".join(p for p in value.split(";") if not p.strip().lower().startswith("domain="))
            out.append((name.encode("latin-1"), value.encode("latin-1")))

        # тело отдаём как пришло (сжатым), поэтому content-length и content-encoding остаются верными
        response = StreamingResponse(resp.aiter_raw(), status_code=resp.status_code,
                                     background=BackgroundTask(resp.aclose))
        response.raw_headers = out
        return response

    @contextlib.asynccontextmanager
    async def lifespan(_):
        yield
        await client.aclose()

    return Starlette(routes=[Route("/{path:path}", proxy, methods=METHODS)], lifespan=lifespan)


class _Server(uvicorn.Server):
    # сигналы ловит основной сервер, иначе Ctrl+C перестанет его останавливать
    def capture_signals(self):
        return contextlib.nullcontext()


class LanProxy:
    def __init__(self, app: Starlette, sock: socket.socket):
        self.port = sock.getsockname()[1]
        self.server = _Server(uvicorn.Config(app, log_level="warning", access_log=False, lifespan="on"))
        self.task = None
        self.sock = sock

    async def _run(self):
        try:
            await self.server.serve(sockets=[self.sock])
        except SystemExit:  # uvicorn выходит через sys.exit при ошибке старта — основную панель не роняем
            log.error("Прокси LAN-панели не запустился")

    def start(self):
        self.task = asyncio.create_task(self._run())

    async def stop(self):
        self.server.should_exit = True
        if self.task:
            await self.task


def start(upstream: str, host: str, port: int, allowed, cookie_name: str) -> LanProxy | None:
    """Поднимает прокси в текущем цикле событий. Порт занят — None, панель откроется в новой вкладке."""
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
    except OSError as e:
        sock.close()
        log.error("Порт %s:%s для прокси LAN-панели занят (%s) — панель будет открываться в новой вкладке",
                  host, port, e.strerror)
        return None
    proxy = LanProxy(build_app(upstream, allowed, cookie_name), sock)
    proxy.start()
    log.info("LAN-панель %s доступна через прокси на %s:%s", upstream, host, proxy.port)
    return proxy
