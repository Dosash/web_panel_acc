"""Чистые функции без Telegram: разбор настроек, ссылок, прав, кнопок, уборка кэша."""
import time
from pathlib import Path

import pytest
from telethon import types

from app import cache, poster, updates
from app.config import normalize_prefix
from app.manager import parse_proxy
from app.tdata_import import _safe_rel, _wanted


# ---------- config ----------

@pytest.mark.parametrize("raw, expected", [
    ("", ""), ("/", ""), ("accounts", "/accounts"), ("/accounts/", "/accounts"), ("a/b", "/a/b"),
])
def test_normalize_prefix(raw, expected):
    assert normalize_prefix(raw) == expected


@pytest.mark.parametrize("raw", ["..", "/a/../b", "про бел", "a?b"])
def test_normalize_prefix_rejects(raw):
    with pytest.raises(ValueError):
        normalize_prefix(raw)


# ---------- прокси ----------

def test_parse_proxy():
    assert parse_proxy("") is None
    p = parse_proxy("socks5://user:pass@1.2.3.4:1080")
    assert p == {"proxy_type": "socks5", "addr": "1.2.3.4", "port": 1080, "username": "user", "password": "pass",
                 "rdns": True}
    assert parse_proxy("1.2.3.4:1080")["proxy_type"] == "socks5"
    assert parse_proxy("http://h:8080")["proxy_type"] == "http"
    with pytest.raises(ValueError):
        parse_proxy("socks5://host-without-port")


# ---------- ссылки t.me ----------

def test_parse_tg_link():
    from app.main import parse_tg_link
    assert parse_tg_link("https://t.me/durov") == {"username": "durov", "post": None, "app": None, "start": None,
                                                   "startapp": None}
    assert parse_tg_link("t.me/durov/15")["post"] == 15
    assert parse_tg_link("https://t.me/s/durov")["username"] == "durov"
    assert parse_tg_link("https://t.me/+AbCdEf123") == {"invite": "AbCdEf123"}
    assert parse_tg_link("https://t.me/joinchat/XyZ") == {"invite": "XyZ"}
    assert parse_tg_link("https://t.me/c/123456/7") == {"channel_id": 123456, "post": 7}
    assert parse_tg_link("https://t.me/somebot/app?startapp=ref1")["startapp"] == "ref1"
    assert parse_tg_link("https://t.me/somebot/app")["app"] == "app"
    assert parse_tg_link("tg://resolve?domain=durov&post=3") == {"username": "durov", "post": 3, "app": None,
                                                                "start": None, "startapp": None}
    assert parse_tg_link("tg://join?invite=Q") == {"invite": "Q"}
    # служебные пути и чужие сайты — не канал
    assert parse_tg_link("https://t.me/addstickers/pack") == {}
    assert parse_tg_link("https://example.com/durov") == {}
    assert parse_tg_link("https://t.me/ab") == {}   # короче 5 символов — не имя


# ---------- права и разрешения ----------

def test_permissions_roundtrip():
    from app.main import PERMISSIONS, banned_rights, permissions_dict
    allowed = {k: True for k in PERMISSIONS}
    allowed["send_photos"] = False
    allowed["stickers"] = False
    rights = banned_rights(allowed)
    assert rights.send_photos and rights.send_stickers and rights.send_gifs
    assert not rights.send_plain and not rights.send_media
    back = permissions_dict(rights)
    assert back == allowed

    # всё медиа запрещено → старый общий флаг send_media тоже выставлен
    none_media = {k: (not k.startswith("send_") or k == "send_plain") and k != "stickers" for k in PERMISSIONS}
    assert banned_rights(none_media).send_media
    # None (без ограничений) → всё разрешено
    assert all(permissions_dict(None).values())


def test_rights_dict():
    from app.main import ADMIN_RIGHTS, my_rights, rights_dict
    assert rights_dict(None) == {}
    r = rights_dict(types.ChatAdminRights(post_messages=True))
    assert r["post_messages"] and not r["ban_users"] and set(r) == set(ADMIN_RIGHTS)
    creator = types.Channel(id=1, title="x", photo=None, date=None, creator=True)
    assert all(my_rights(creator).values())


# ---------- оформленные посты ----------

def test_normalize_url():
    assert poster.normalize_url("example.com/a") == "https://example.com/a"
    assert poster.normalize_url("https://t.me/x") == "https://t.me/x"
    assert poster.normalize_url("tg://resolve?domain=x") == "tg://resolve?domain=x"
    assert poster.normalize_url("javascript:alert(1)") == ""
    assert poster.normalize_url("localhost") == ""   # без точки — не адрес
    assert poster.normalize_url("") == ""


def test_markup():
    assert poster.markup(None) is None
    assert poster.markup([[]]) is None
    m = poster.markup([[{"text": "Сайт", "url": "example.com", "style": "primary"}, {"text": "Код", "copy": "abc"}]])
    row = m.rows[0]
    assert len(row.buttons) == 2
    assert isinstance(row.buttons[0].type, types.InlineButtonTypeUrl)
    assert row.buttons[0].style.bg_primary
    assert isinstance(row.buttons[1].type, types.InlineButtonTypeCopy)
    assert row.buttons[1].style is None
    with pytest.raises(ValueError):
        poster.markup([[{"text": "", "url": "example.com"}]])
    with pytest.raises(ValueError):
        poster.markup([[{"text": "x", "url": ""}]])
    with pytest.raises(ValueError):
        poster.markup([[{"text": "x", "url": "example.com"}] * (poster.ROW_LIMIT + 1)])


def test_entities():
    ents = poster.entities([
        {"type": "bold", "offset": 0, "length": 3},
        {"type": "link", "offset": 4, "length": 2, "url": "example.com"},
        {"type": "link", "offset": 4, "length": 2, "url": "javascript:x"},   # плохая ссылка — пропускается
        {"type": "pre", "offset": 0, "length": 1, "language": "py"},
        {"type": "quote", "offset": 0, "length": 1, "collapsed": True},
        {"type": "nope", "offset": 0, "length": 1},
        {"type": "bold", "offset": -1, "length": 1},
    ])
    kinds = [type(e) for e in ents]
    assert kinds == [types.MessageEntityBold, types.MessageEntityTextUrl, types.MessageEntityPre,
                     types.MessageEntityBlockquote]
    assert ents[1].url == "https://example.com"
    assert ents[3].collapsed is True


# ---------- обновления ----------

def test_parse_version():
    assert updates.parse_version("v0.12.0") == (0, 12, 0)
    assert updates.parse_version("1.2") == (1, 2)
    assert updates.parse_version("0.12.1") > updates.parse_version("0.9.9")


# ---------- tdata ----------

def test_safe_rel_and_wanted():
    assert _safe_rel("tdata/key_datas") == Path("tdata/key_datas")
    assert _safe_rel("tdata\\D877F783D5D3EF8C\\maps") == Path("tdata/D877F783D5D3EF8C/maps")
    assert _safe_rel("../etc/passwd") is None
    assert _safe_rel("/etc/passwd") is None
    assert _safe_rel("") is None
    assert _wanted(Path("tdata/key_datas"), 100)
    assert not _wanted(Path("tdata/user_data/x"), 100)
    assert not _wanted(Path("tdata/emoji/cache"), 100)
    assert not _wanted(Path("tdata/big"), 100 * 1024 * 1024)


# ---------- уборка кэша ----------

def _touch(path: Path, age: float, size: int = 10) -> None:
    path.write_bytes(b"x" * size)
    import os
    os.utime(path, (time.time() - age, time.time() - age))


def test_clean_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    _touch(tmp_path / "m_1_2_3.jpg", 8 * 86400)          # медиа старше недели — удалить
    _touch(tmp_path / "m_1_2_4.jpg", 86400)              # свежее — оставить
    _touch(tmp_path / "a_1_5.jpg", 8 * 86400)            # аватар живёт месяц — оставить
    _touch(tmp_path / "a_1_6.jpg", 40 * 86400)           # старше месяца — удалить
    removed, freed = cache.clean_cache(max_bytes=0)
    assert removed == 2 and freed == 20
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a_1_5.jpg", "m_1_2_4.jpg"]


def test_clean_cache_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    _touch(tmp_path / "m_old.jpg", 3600, size=60)
    _touch(tmp_path / "m_new.jpg", 60, size=60)
    removed, freed = cache.clean_cache(max_bytes=100)
    assert removed == 1 and freed == 60
    assert [p.name for p in tmp_path.iterdir()] == ["m_new.jpg"]   # удалён самый старый


def test_clean_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "TMP_DIR", tmp_path)
    old = tmp_path / "old"
    old.mkdir()
    _touch(old / "f", 2 * 3600)
    import os
    os.utime(old, (time.time() - 2 * 3600,) * 2)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    assert cache.clean_tmp() == 1
    assert not old.exists() and fresh.exists()
