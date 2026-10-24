"""HTTP-слой панели без Telegram: вход, защита, папки, статика, боты, WebSocket."""
import app.main as main
from tests.conftest import PASSWORD


def test_health_without_auth(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["accounts"] == 0 and body["bots"] == {}
    assert body["version"] == main.VERSION


def test_protected_endpoints_require_login(client):
    client.cookies.clear()
    for path in ("/api/accounts", "/api/session", "/api/folders", "/api/bots", "/api/dialogs"):
        assert client.get(path).status_code == 401, path


def test_login_logout(client):
    client.cookies.clear()
    main._login_failures.clear()
    assert client.post("/api/login", json={"password": "wrong"}).status_code == 401
    r = client.post("/api/login", json={"password": PASSWORD})
    assert r.status_code == 200 and "panel_auth" in r.cookies
    sess = client.get("/api/session").json()
    assert sess == {"ok": True, "auth": True, "version": main.VERSION}
    client.post("/api/logout")
    client.cookies.clear()
    assert client.get("/api/session").status_code == 401


def test_login_rate_limit(client, monkeypatch):
    client.cookies.clear()
    main._login_failures.clear()
    monkeypatch.setattr(main.asyncio, "sleep", _no_sleep)
    for _ in range(main.LOGIN_ATTEMPTS):
        assert client.post("/api/login", json={"password": "wrong"}).status_code == 401
    r = client.post("/api/login", json={"password": PASSWORD})   # даже верный пароль — ждать
    assert r.status_code == 429 and "Retry-After" in r.headers
    main._login_failures.clear()
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 200
    client.post("/api/logout")
    client.cookies.clear()


async def _no_sleep(_):
    return None


def test_login_blocked_window():
    main._login_failures.clear()
    now = 1_000_000.0
    for i in range(main.LOGIN_ATTEMPTS):
        main._login_failures.append(now - 100 + i)
    assert main.login_blocked(now) > 0
    assert main.login_blocked(now + main.LOGIN_WINDOW + 1) == 0   # старые попытки забыты
    main._login_failures.clear()


def test_folders_crud(authed):
    r = authed.post("/api/folders", json={"name": "  Работа  "})
    assert r.status_code == 200
    folder = r.json()
    assert folder["name"] == "Работа" and folder["items"] == []
    fid = folder["id"]
    assert authed.post("/api/folders", json={"name": "   "}).status_code == 400

    r = authed.post(f"/api/folders/{fid}/items", json={"account_id": 1, "chat_id": -100123})
    assert r.json()["items"] == [{"account_id": 1, "chat_id": -100123}]
    # повторное добавление не дублирует
    r = authed.post(f"/api/folders/{fid}/items", json={"account_id": 1, "chat_id": -100123})
    assert len(r.json()["items"]) == 1
    r = authed.delete(f"/api/folders/{fid}/items", params={"account_id": 1, "chat_id": -100123})
    assert r.json()["items"] == []

    assert authed.patch(f"/api/folders/{fid}", json={"name": "Личное"}).json()["name"] == "Личное"
    assert any(f["id"] == fid for f in authed.get("/api/folders").json())
    assert authed.delete(f"/api/folders/{fid}").json() == {"ok": True}
    assert authed.delete(f"/api/folders/{fid}").status_code == 404
    # папка без аккаунта в сети даёт пустой список, а не ошибку
    assert authed.get("/api/dialogs", params={"folder_id": fid}).json() == []


def test_unknown_account_is_404(authed):
    r = authed.get("/api/accounts/999/profile")
    assert r.status_code == 404 and "999" in r.json()["detail"]
    assert authed.post("/api/accounts/999/reconnect").status_code == 404
    assert authed.get("/api/accounts/999/avatar/me").status_code == 404
    assert authed.get("/api/accounts/999/avatar/abc").status_code == 400


def test_dialogs_without_accounts(authed):
    assert authed.get("/api/dialogs").json() == []
    assert authed.get("/api/dialogs", params={"limit": 10_000}).status_code == 200


def test_static_is_revalidated(client):
    for path in ("/", "/app.js", "/app.css"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", path
    assert "TG Panel" in client.get("/").text


def test_bots_list_and_validation(authed):
    bots = {b["name"]: b for b in authed.get("/api/bots").json()}
    assert set(bots) == {"posts", "ads"}
    assert all(not b["configured"] and b["status"] == "off" for b in bots.values())
    assert authed.get("/api/bots/nope/log").status_code == 404
    assert authed.get("/api/bots/posts/log").json() == {"lines": []}
    r = authed.put("/api/bots/posts", json={"admin_ids": [], "timezone": "Mars/Olympus"})
    assert r.status_code == 400 and "часовой пояс" in r.json()["detail"]
    r = authed.put("/api/bots/posts", json={"token": "abc", "admin_ids": [], "timezone": "Europe/Moscow"})
    assert r.status_code == 400 and "токен" in r.json()["detail"].lower()
    r = authed.put("/api/bots/posts", json={"admin_ids": [], "timezone": "Europe/Moscow"})
    assert r.status_code == 400   # токена нет — настраивать нечего
    assert authed.post("/api/bots/posts/start").status_code == 400


def test_bot_panel_when_bot_is_off(authed):
    r = authed.get("/bots/posts/")
    assert r.status_code == 503 and "выключен" in r.text
    r = authed.get("/bots/posts", follow_redirects=False)
    assert r.status_code in (301, 302, 307) and r.headers["location"].endswith("/bots/posts/")
    assert authed.get("/bots/nope/").status_code == 404


def test_bot_panel_requires_login(client):
    client.cookies.clear()
    assert client.get("/bots/posts/").status_code == 401


def test_websocket(authed):
    with authed.websocket_connect("/ws") as ws:
        ws.send_text("ping")


def test_websocket_rejects_guests(client):
    import pytest
    from starlette.websockets import WebSocketDisconnect
    client.cookies.clear()
    with pytest.raises(WebSocketDisconnect) as e, client.websocket_connect("/ws"):
        pass
    assert e.value.code == 4401


def test_import_sessions_validation(authed):
    r = authed.post("/api/accounts/import-sessions", data={"name": "x"},
                    files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert r.status_code == 400 and "нет сессии" in r.json()["detail"]
    r = authed.post("/api/accounts/import-sessions", data={"name": "x"},
                    files=[("files", ("a.session", b"garbage", "application/octet-stream"))])
    assert r.status_code == 400
    r = authed.post("/api/accounts/import-sessions", data={"name": "x"},
                    files=[("files", ("a.session", b"SQLite format 3\x00" + b"\x00" * 50, "application/octet-stream"))])
    assert r.status_code == 400 and "повреждён" in r.json()["detail"]


def test_import_sessions_requires_login(client):
    r = client.post("/api/accounts/import-sessions", files=[("files", ("a.session", b"x", "application/octet-stream"))])
    assert r.status_code == 401
