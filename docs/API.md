# API

Все эндпоинты, кроме `/api/login` и `/api/logout`, требуют cookie `panel_auth`
(если в `.env` задан `PANEL_PASSWORD`). Ошибки возвращаются как `{"detail": "текст"}`.

Обозначения: `aid` — id аккаунта в панели, `cid` — id чата в формате Telethon
(пользователь `123`, группа `-123`, канал/супергруппа `-100123`), `mid` — id сообщения.

| Код | Когда |
|---|---|
| 400 | Ошибка Telegram (`Telegram: FLOOD_WAIT_...`), неверные данные |
| 401 | Нужен вход в панель |
| 404 | Аккаунт/медиа не найдены |
| 409 | Аккаунт не подключён (`status` не `online`) |

## Вход

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| POST | `/api/login` | `{password}` | `{ok}` + cookie |
| POST | `/api/logout` | — | `{ok}` |
| GET | `/api/session` | — | `{ok, auth, lan_panel}` — `auth: false`, если пароль отключён |

`lan_panel` — веб-панель из локальной сети для кнопки в рейке: `{name, url, proxy_port}` или `null`,
если `LAN_PANEL_URL` пуст. `proxy_port` — порт прокси для iframe; `0` — прокси не запущен
(выключен или порт занят), панель открывается в новой вкладке по `url`.

## Прокси веб-панели из локальной сети

Отдельный сервер в том же процессе на `HOST:LAN_PANEL_PROXY_PORT` (не на основном порту).
Любой путь и метод проксируется на `LAN_PANEL_URL` как есть: query, тело, cookies, заголовки
(`Origin`/`Referer` переписываются на адрес сервера). Из ответа убираются `X-Frame-Options`,
`Strict-Transport-Security` и директива `frame-ancestors` в CSP; абсолютные редиректы на сервер
становятся относительными, у `Set-Cookie` убирается `Domain`. WebSocket не проксируется.

| Код | Когда |
|---|---|
| 401 | Нет cookie `panel_auth` (cookie привязана к хосту, порт не важен) |
| 502 | Сервер панели не отвечает |

## Аккаунты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/accounts` | Список: `id, name, color, proxy, user_id, phone, username, full_name, status, error` |
| POST | `/api/accounts/import` | multipart: `name`, `files[]` (файлы tdata с относительными путями или zip), `new_session`, `password_2fa`, `passcode`, `proxy`. Ответ — аккаунт + `updated` |
| PATCH | `/api/accounts/{aid}` | `{name?, color?, proxy?}`; смена прокси переподключает |
| POST | `/api/accounts/{aid}/reconnect` | Переподключить |
| DELETE | `/api/accounts/{aid}?logout=bool` | Удалить из панели; `logout=true` — ещё и завершить сеанс в Telegram |
| GET | `/api/accounts/{aid}/profile` | `first_name, last_name, username, phone, about, premium` |
| POST | `/api/accounts/{aid}/profile` | `{first_name?, last_name?, about?, username?}` |
| POST | `/api/accounts/{aid}/photo` | multipart `file` — новый аватар |
| GET | `/api/accounts/{aid}/authorizations` | Активные сеансы: `hash` (строка), `current`, `device`, `app`, `ip`, `country`, `active` |
| DELETE | `/api/accounts/{aid}/authorizations/{hash}` | Завершить сеанс |
| GET | `/api/accounts/{aid}/avatar/{peer}` | JPEG аватара (`peer` = id или `me`); 404 — фото нет |

## Диалоги и чаты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/dialogs?account_id=&archived=&limit=100&folder_id=` | Диалоги одного или всех аккаунтов; закреплённые сверху, дальше по дате. С `folder_id` — только чаты этой папки панели (запрашиваются точечно, даже если далеко за первой сотней) |
| POST | `/api/accounts/{aid}/chats/{cid}/pin` | `{pinned}` — закрепить/открепить чат в Telegram (лимит 5, с Premium 10) |
| POST | `/api/accounts/{aid}/chats/{cid}/mute` | `{muted}` — выключить уведомления навсегда / включить |
| POST | `/api/accounts/{aid}/chats/{cid}/archive` | `{archived}` — в архив / из архива |
| GET | `/api/accounts/{aid}/chats/{cid}` | Описание чата: `title, type, username, about, members, is_admin, can_send, phone` |
| POST | `/api/accounts/{aid}/chats/{cid}/read` | Отметить прочитанным |
| POST | `/api/accounts/{aid}/chats/{cid}/edit` | `{title?, about?, username?}` — для админа группы/канала |
| POST | `/api/accounts/{aid}/chats/{cid}/photo` | multipart `file` — фото группы/канала |
| POST | `/api/accounts/{aid}/chats/{cid}/invite` | Создать ссылку-приглашение → `{link}` |
| POST | `/api/accounts/{aid}/chats/{cid}/leave` | Покинуть группу/канал или удалить личный чат |
| GET | `/api/accounts/{aid}/search?q=` | Поиск людей и чатов (по @username, имени, номеру) |
| POST | `/api/accounts/{aid}/join` | `{link}` — `t.me/+hash`, `t.me/joinchat/hash`, `@name`, `t.me/name` |
| POST | `/api/accounts/{aid}/channels` | `{title, about, kind: channel|group, username?}` → `{id, title, type, warning}` |

Объект диалога: `account_id, id, title, type (user|bot|group|channel), username, unread, mentions,
pinned, archived, muted, date, last_text, last_media, last_action, last_out, is_creator, is_admin, verified`.

## Папки панели

Папки хранятся в базе панели (не в Telegram), поэтому в одной папке могут быть чаты разных аккаунтов.
При удалении аккаунта его чаты убираются из всех папок.

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/folders` | `[{id, name, position, items: [{account_id, chat_id}]}]` |
| POST | `/api/folders` | `{name}` — создать (до 40 символов) |
| PATCH | `/api/folders/{id}` | `{name}` — переименовать |
| DELETE | `/api/folders/{id}` | Удалить папку (чаты не трогаются) |
| POST | `/api/folders/{id}/items` | `{account_id, chat_id}` — добавить чат; повтор игнорируется |
| DELETE | `/api/folders/{id}/items?account_id=&chat_id=` | Убрать чат из папки |

## Сообщения

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/accounts/{aid}/chats/{cid}/messages?offset_id=&limit=40` | История (старые → новые). `offset_id` — подгрузка более ранних |
| POST | `/api/accounts/{aid}/chats/{cid}/messages` | `{text, reply_to?, silent?, no_preview?}` |
| POST | `/api/accounts/{aid}/chats/{cid}/files` | multipart: `file`, `caption`, `reply_to`, `as_document` |
| PATCH | `/api/accounts/{aid}/chats/{cid}/messages/{mid}` | `{text}` — редактировать |
| DELETE | `/api/accounts/{aid}/chats/{cid}/messages/{mid}?revoke=true` | Удалить (у всех / только у себя) |
| POST | `/api/accounts/{aid}/chats/{cid}/messages/{mid}/pin?unpin=bool` | Закрепить/открепить |
| POST | `/api/accounts/{aid}/chats/{cid}/messages/{mid}/forward` | `{to_chat_id}` — переслать в другой чат того же аккаунта |
| POST | `/api/accounts/{aid}/chats/{cid}/messages/{mid}/click` | `{row, col}` — нажать callback-кнопку или кнопку игры → `{message, alert, url}`. Кнопки-ссылки открывает браузер, сюда их не шлют |
| GET | `/api/accounts/{aid}/chats/{cid}/messages/{mid}/media?thumb=bool` | Файл медиа (кэшируется на диске) |

Объект сообщения: `account_id, chat_id, id, date, edit_date, out, text, entities, buttons, sender_id,
sender_name, reply_to, media, action, views, pinned`.

- `media`: `{type: photo|video|gif|round|voice|audio|file|sticker|webpage|poll|geo|contact, name?, size?, mime?, w?, h?, spoiler?}`;
  для `webpage` — `{url, site, title, description}`.
- `entities` — форматирование текста: `{type, offset, length, url?, language?, user_id?}`, где `type` —
  `bold|italic|underline|strike|code|pre|spoiler|quote|link|url|email|phone|mention|mention_name|hashtag|command`.
  Смещения в UTF-16 (совпадают с индексами строк JavaScript).
- `buttons` — inline-кнопки: массив рядов, кнопка `{text, kind, url?, copy?}`, где `kind` —
  `url|webview|callback|password|game|switch|copy|profile|buy|disabled|other`. `null`, если кнопок нет.

## WebSocket `/ws`

Сервер присылает JSON-события; клиент раз в 25 секунд шлёт `ping`.

| `type` | Поля | Когда |
|---|---|---|
| `account` | `account` (как в `/api/accounts`) | Сменился статус аккаунта |
| `message` | `message`, `chat_title`, `chat_type` | Новое входящее или исходящее сообщение |
| `edit` | `message` | Сообщение отредактировано |
| `delete` | `account_id`, `chat_id` (может быть `null` для личных чатов), `ids` | Сообщения удалены |
| `read` | `account_id`, `chat_id`, `max_id`, `outbox` | Собеседник прочитал ваши сообщения |
