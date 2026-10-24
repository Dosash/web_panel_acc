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
- `bots/posts`, `bots/ads` — встроенные бот постинга и бот рекламы (бывшие post_channel_bot, ads_chanel_bot):
  отдельные процессы, их запускает и проксирует `app/bots.py`. Импорты внутри — `bots.posts.…`/`bots.ads.…`.
- `desktop/` — программа для Linux/macOS (PyQt5 WebEngine + тот же `app/`), см. `desktop/README.md`.
  `desktop-win/` — программа для Windows: оболочка Tauri 2 + WebView2 (Rust) и серверная часть отдельным процессом
  (PyInstaller, из Qt только QtCore), см. `desktop-win/README.md`; сборка — `desktop-win\build.ps1`.
  Выпуск: повысить `VERSION` в `app/config.py` + раздел в `CHANGELOG.md` → после merge в main CI публикует
  релиз под все ОС (+ `TG-Panel-<версия>-SHA256SUMS.txt`), установленные программы обновляются сами.
  Новый модуль, который `app/` грузит по имени, может понадобиться в `hiddenimports` в `desktop/tg-panel.spec`
  и `desktop-win/server/tg-panel-server.spec`.
