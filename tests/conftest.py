"""Общие фикстуры. Настройки панели читаются из окружения при импорте app.config — задаём их до импорта."""
import os
import tempfile

import pytest

_DATA = tempfile.mkdtemp(prefix="tg-panel-test-")
os.environ.update(DATA_DIR=_DATA, WEB_PASSWORD="test-password", WEB_HOST="127.0.0.1", WEB_PREFIX="",
                  UPDATE_CHECK="0", CACHE_MAX_MB="1")

PASSWORD = "test-password"


@pytest.fixture(scope="session")
def client():
    """Приложение с lifespan: без аккаунтов и без ботов (их настроек в пустой DATA_DIR нет)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed(client):
    """Тот же клиент, но после входа; cookie снимается после теста."""
    import app.main as main

    main._login_failures.clear()
    r = client.post("/api/login", json={"password": PASSWORD})
    assert r.status_code == 200
    yield client
    client.post("/api/logout")
    client.cookies.clear()
