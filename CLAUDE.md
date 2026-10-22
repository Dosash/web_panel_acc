# TG Panel — заметки для работы над проектом

Веб-панель для нескольких Telegram-аккаунтов, импорт из tdata. Python 3.12 + FastAPI + Telethon + opentele,
фронтенд без сборки (`static/`). Подробности: `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/API.md`.

- Интерфейс, ошибки и комментарии — на русском.
- После правок в `app/` сервер нужно перезапустить; `static/` — достаточно F5.
- Цвета в CSS — только через токены из `:root` (обе темы). Иконки — словарь `ICONS` в `app.js`.
- opentele бросает `BaseException` — см. `_reraise_fatal` в `app/tdata_import.py`.
- Чат по id брать через `manager.entity(aid, cid)` (кэш сущностей пуст после перезапуска).
- Изменения отмечать в `CHANGELOG.md`, новые эндпоинты — в `docs/API.md`, планы — в `docs/ROADMAP.md`.
- `data/` и `.env` содержат секреты (ключ шифрования сессий) — не коммитить и не выводить.
- Адреса в `static/` — только относительные (`api/...`, `ws`): панель может стоять под путём `WEB_PREFIX`.
