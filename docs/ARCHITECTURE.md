# Архитектура

## Общая схема

```
Браузер (static/)  ──REST──▶  FastAPI (app/main.py)  ──▶  Manager (app/manager.py)  ──MTProto──▶  Telegram
       ▲                            │                           │  по одному TelegramClient
       └──────── WebSocket /ws ◀────┴──── Hub (события) ◀───────┘  на каждый аккаунт
                                    │
                                    ▼
                          storage.py → SQLite data/panel.db (сессии зашифрованы Fernet)
```

Один процесс Python держит постоянные MTProto-соединения со всеми аккаунтами. Поэтому панель
нельзя запускать на serverless-хостинге — нужен постоянно работающий процесс (свой ПК, VPS).

## Модули

### `app/config.py`
Читает `.env` (`WEB_HOST`, `WEB_PORT`, `WEB_PASSWORD`, `WEB_PREFIX`, `HUB_URL`, `DATA_DIR`; старые имена
`HOST`, `PORT`, `PANEL_PASSWORD` — как запасные), создаёт папки `data/`, `data/cache/`, `data/tmp/`. При первом запуске генерирует
`data/secret.key` (ключ Fernet для сессий) и `data/cookie.key` (подпись cookie), права `600`.

### `app/storage.py`
Таблица `accounts` в SQLite. Поле `session_enc` — строка `StringSession` Telethon, зашифрованная
Fernet. Поле `api_json` — «отпечаток» клиента (api_id, модель устройства, версия ОС и т.д.),
с которым аккаунт был авторизован; при каждом подключении используются те же параметры,
чтобы Telegram видел одно и то же устройство.

### `app/tdata_import.py` — tdata → сессия
1. `save_upload` сохраняет присланные файлы (или распаковывает zip) во временную папку
   `data/tmp/<uuid>/`, пропуская кэш (`user_data`, `emoji`, …), файлы > 5 МБ и пути с `..`.
2. `find_tdata_root` ищет папку с `key_datas`.
3. `convert` через **opentele** читает tdata и получает ключ авторизации:
   - **Отдельный сеанс** (`new_session=True`): клиент на ключе из tdata подтверждает вход
     нового клиента через QR-логин (`QRLoginToNewClient`). В Telegram появляется новое
     устройство, tdata остаётся рабочей. Нужен облачный пароль, если включена 2FA.
   - **Тот же ключ**: берётся ключ авторизации из tdata как есть. Быстрее, но если tdata
     одновременно используется в Telegram Desktop с другого IP, Telegram может сбросить сеанс.
4. Проверяет сессию через `get_me()` и возвращает `(StringSession, api, me)`.
5. Временная папка удаляется в любом случае (`finally`).

Параметры устройства генерируются `API.TelegramDesktop.Generate(system="windows")` — клиент
представляется официальным Telegram Desktop.

### `app/manager.py`
- `Manager` — словарь `Live` по id аккаунта. `Live` хранит клиент, статус
  (`offline | connecting | online | error`) и текст ошибки.
- `start(account)` создаёт `opentele.tl.TelegramClient` с `StringSession` и параметрами из
  `api_json`, подключается, проверяет авторизацию, обновляет phone/username в БД,
  подписывается на события.
- События Telethon (`NewMessage`, `MessageEdited`, `MessageDeleted`, `MessageRead`)
  превращаются в JSON и рассылаются всем WebSocket-клиентам через `Hub`.
- `entity(account_id, chat_id)` — получение собеседника по id. Кэш сущностей у `StringSession`
  живёт только в памяти, поэтому после перезапуска при промахе один раз загружаются все
  диалоги (`get_dialogs(limit=None)`), и запрос повторяется.
- `media_slot(account_id)` — семафор (4 одновременные загрузки на аккаунт) против flood wait.
- `message_dict` / `dialog_dict` / `media_info` — сериализация объектов Telethon в JSON для фронтенда.

### `app/main.py`
FastAPI-приложение: REST API (см. [API.md](API.md)), WebSocket `/ws`, раздача `static/`.
- Авторизация панели — подписанная cookie `panel_auth` (itsdangerous, 30 дней) на пути панели.
  Если `WEB_PASSWORD` пуст, проверка отключена.
- `WEB_PREFIX`: `PrefixMiddleware` выставляет `root_path` для запросов под префиксом (nginx передаёт путь как есть),
  `/accounts` без слэша перенаправляется на `/accounts/`. Интерфейс использует только относительные адреса.
- `GET /api/health` — без входа, для `HEALTHCHECK` Docker и карточки в хабе панелей.
- Обработчики исключений превращают `RPCError` Telethon в `400 {"detail": "Telegram: ..."}`,
  «аккаунт не подключён» (`RuntimeError`) в `409`.
- Кэш медиа: `data/cache/m_<aid>_<chat>_<msg>[_t].<ext>`, аватары `a_<aid>_<peer>.jpg`
  (TTL сутки), отметка «фото нет» `a_<aid>_<peer>.none` (TTL сутки).

### `static/` — интерфейс
Без сборки и фреймворков: `index.html` (каркас), `app.css` (дизайн-система), `app.js` (логика).
- Состояние — объект `S` (аккаунты, текущий scope, диалоги, открытый чат, сообщения).
- Рендер — функции `renderRail`, `renderDialogs`, `renderMessages` пересобирают свои блоки.
  Новые сообщения добавляются точечно (`appendMessage`/`replaceMessage`) без перерисовки ленты.
- Аватары грузятся лениво через `IntersectionObserver`.
- Иконки — inline SVG из словаря `ICONS`, вставляются по атрибуту `data-icon`.
- Настройки интерфейса (тема, невидимка) — в `localStorage`.

## Потоки данных

**Открытие чата:** `openChat` → `GET /chats/{cid}/messages` → рендер →
(если невидимка выключена) `POST /chats/{cid}/read` → параллельно `GET /chats/{cid}` за описанием.

**Входящее сообщение:** Telegram → `events.NewMessage` → `Hub.send({"type": "message"})` →
`onEvent` в браузере → обновление строки диалога и, если чат открыт, `appendMessage`.

**Отправка:** `POST /chats/{cid}/messages` → `client.send_message` → ответ сразу рисуется;
дубль от события `NewMessage` отбрасывается по id (`replaceMessage`).

## Развёртывание

Docker-образ на `python:3.12-slim` (+ `libglib2.0-0` для QtCore из PyQt5), сеть хоста, том `./data → /app/data`.
За общим nginx панель стоит под своим путём (`WEB_PREFIX`), nginx должен пропускать WebSocket
(`Upgrade`/`Connection`). Подробно — README, раздел «Доступ к панели».

## Безопасность

- Сессии в БД зашифрованы; ключ в `data/secret.key`. Утечка БД без ключа сессии не раскрывает.
- tdata не хранится.
- По умолчанию сервер слушает только `127.0.0.1`.
- Медиа и аватары отдаются только авторизованному пользователю панели.
- Для доступа извне: включить `WEB_PASSWORD` и ставить панель за HTTPS (Caddy/nginx/Cloudflare Tunnel).
