# API

Все эндпоинты, кроме `/api/login`, `/api/logout` и `/api/health`, требуют cookie `panel_auth`
(если в `.env` задан `WEB_PASSWORD`). Ошибки возвращаются как `{"detail": "текст"}`.

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
| GET | `/api/session` | — | `{ok, auth, version, hub_url}` — `auth: false`, если пароль отключён; `hub_url` — ссылка «Все панели» или пустая строка |
| GET | `/api/health` | — | Без входа. `{status: "ok" \| "degraded", version, accounts, online, errors}` — `degraded`, если есть аккаунты с ошибкой |
| GET | `/api/update?force=` | — | Последний релиз на GitHub: `{current, latest, available, notes, page, published_at, docker, enabled, checked_at, error}`. `available` — релиз новее этой панели; `notes` — описание релиза (Markdown); `docker` — панель в контейнере. Ответ GitHub кэшируется на 6 часов (после ошибки — 15 минут); `force=1` — спросить заново (не чаще раза в минуту). При `UPDATE_CHECK=0` — только `{current, enabled: false, available: false, docker}` |

Если задан `WEB_PREFIX` (например, `/accounts`), все пути — с ним: `/accounts/api/session`, `/accounts/ws`.
Без префикса панель тоже отвечает (для проверок на самом сервере).

## Аккаунты

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/accounts` | Список: `id, name, color, proxy, user_id, phone, username, full_name, status, error` |
| POST | `/api/accounts/import` | multipart: `name`, `files[]` (файлы tdata с относительными путями или zip), `new_session`, `password_2fa`, `passcode`, `proxy`. Ответ — аккаунт + `updated` |
| PATCH | `/api/accounts/{aid}` | `{name?, color?, proxy?}`; смена прокси переподключает |
| POST | `/api/accounts/{aid}/reconnect` | Переподключить |
| POST | `/api/accounts/{aid}/read_all` | Отметить прочитанными все чаты аккаунта (и архив, и упоминания) → `{ok, count}` |
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
| GET | `/api/accounts/{aid}/chats/{cid}` | Описание чата: `title, type, username, about, members, is_admin, can_send, phone`; у каналов и групп `joined`, у ботов `webapp` (`{mode, text, url}` или `null`). Для админа группы/канала ещё `invite` (основная ссылка), `my_rights` (права аккаунта), `settings` (см. ниже), `legacy: true` у обычной (не супер-) группы |
| POST | `/api/accounts/{aid}/chats/{cid}/read` | Отметить прочитанным до последнего сообщения |
| POST | `/api/accounts/{aid}/chats/{cid}/edit` | `{title?, about?, username?}` — для админа группы/канала |
| POST | `/api/accounts/{aid}/chats/{cid}/photo` | multipart `file` — фото группы/канала |
| POST | `/api/accounts/{aid}/chats/{cid}/invite` | Создать ссылку-приглашение → `{link}` |
| POST | `/api/accounts/{aid}/chats/{cid}/leave` | Покинуть группу/канал или удалить личный чат |
| POST | `/api/accounts/{aid}/chats/{cid}/settings` | `{signatures?, noforwards?, slowmode?, hidden_prehistory?, permissions?}` — только изменённые поля; ответ как у описания чата |
| GET | `/api/accounts/{aid}/chats/{cid}/admins` | Админы канала/супергруппы: `id, name, username, bot, self, rank, creator, can_edit, rights` |
| POST | `/api/accounts/{aid}/chats/{cid}/admins` | `{user, rights, rank}` — назначить или изменить права; `user` — `@username`, `t.me/…`, телефон контакта или id. Ответ — новый список |
| DELETE | `/api/accounts/{aid}/chats/{cid}/admins/{uid}` | Снять права администратора → новый список |
| DELETE | `/api/accounts/{aid}/chats/{cid}` | Удалить канал/супергруппу целиком (только владелец) |
| GET | `/api/accounts/{aid}/search?q=` | Поиск людей и чатов (по @username, имени, номеру) |
| POST | `/api/accounts/{aid}/join` | `{link}` — `t.me/+hash`, `t.me/joinchat/hash`, `@name`, `t.me/name`; или `{chat_id}` — публичный канал, найденный через `/resolve` |
| GET | `/api/accounts/{aid}/resolve?link=` | Ссылка `t.me/…` или `tg://…` → карточка: `kind` (`chat`, `invite`, `external` — открыть в браузере), `id, title, type, username, verified, about, members, joined, webapp`; для ссылок на бота и пост ещё `post, app, start, startapp`; у приглашений `invite, request_needed` |
| POST | `/api/accounts/{aid}/webapp` | `{bot, mode: button\|menu\|main\|app, chat_id?, url?, app?, start_param?, theme?}` → `{url, query_id, bot_id, title}` — адрес мини-приложения с подписанными данными пользователя для фрейма |
| POST | `/api/accounts/{aid}/webapp/prolong` | `{bot, query_id, chat_id?}` — раз в минуту, пока открыто приложение из кнопки или меню бота |
| POST | `/api/accounts/{aid}/channels` | `{title, about, kind: channel|group, username?}` → `{id, title, type, warning}` |

Объект диалога: `account_id, id, title, type (user|bot|group|channel), username, unread, mentions,
pinned, archived, muted, date, last_text, last_media, last_action, last_out, is_creator, is_admin, verified`.

Права администратора (`rights`, `my_rights`) — словарь `true/false`: `change_info, post_messages, edit_messages,
delete_messages, ban_users, invite_users, pin_messages, add_admins, anonymous, manage_call, post_stories,
edit_stories, delete_stories, manage_topics, other`.

`settings`: `signatures` и `slowmode`/`hidden_prehistory` (только каналы и супергруппы), `noforwards`,
`permissions` — что разрешено участникам группы: `send_plain, send_photos, send_videos, stickers, send_audios,
send_docs, send_voices, send_roundvideos, embed_links, send_polls, invite_users, pin_messages, change_info`.
`slowmode` — 0, 10, 30, 60, 300, 900 или 3600 секунд.

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
- `buttons` — inline-кнопки: массив рядов, кнопка `{text, kind, url?, copy?, style?}`, где `style` — цвет,
  заданный ботом (`primary` синяя, `success` зелёная, `danger` красная), а `kind` —
  `url|webview|callback|password|game|switch|copy|profile|buy|disabled|other`. `null`, если кнопок нет.
  Нажатие `webview` через `/click` возвращает `webapp: {bot, mode, url}` — его передают в `/webapp`.

## Оформленные посты

Только для администраторов канала или группы. Пост без кнопок публикует сам аккаунт; с кнопками — бот канала
(у обычного аккаунта Telegram inline-кнопки отбрасывает).

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/accounts/{aid}/chats/{cid}/post` | `{bot: {id, username, admin} \| null, buttons_supported, can_promote}` — бот для кнопок и может ли аккаунт назначать админов |
| POST | `/api/accounts/{aid}/chats/{cid}/post/bot` | `{token}` — подключить бота (токен от @BotFather). Если бот не админ и у аккаунта есть право — назначает его с правом публикации. Пустой `token` — повторить с сохранённым. Ответ как у GET |
| DELETE | `/api/accounts/{aid}/chats/{cid}/post/bot` | Забыть бота канала |
| POST | `/api/accounts/{aid}/chats/{cid}/post` | multipart: `data` (JSON, ниже) и необязательный `file` → объект сообщения или `{scheduled: true}` |

`data`: `{text, entities, buttons, silent?, no_preview?, invert?, spoiler?, schedule?}`.
- `entities` — как в объекте сообщения: `bold|italic|underline|strike|code|pre|spoiler|quote|link` (`url` у `link`).
- `buttons` — ряды кнопок `{text, url | copy, style?}`, `style` — `primary|success|danger`; до 8 в ряду, до 100 всего.
- `invert` — текст над медиа (или превью ссылки над текстом), `spoiler` — медиа под спойлером,
  `schedule` — unix-время публикации (только без кнопок: боты не умеют отложенную отправку).

## WebSocket `/ws`

Сервер присылает JSON-события; клиент раз в 25 секунд шлёт `ping`.

| `type` | Поля | Когда |
|---|---|---|
| `account` | `account` (как в `/api/accounts`) | Сменился статус аккаунта |
| `message` | `message`, `chat_title`, `chat_type` | Новое входящее или исходящее сообщение |
| `edit` | `message` | Сообщение отредактировано |
| `delete` | `account_id`, `chat_id` (может быть `null` для личных чатов), `ids` | Сообщения удалены |
| `read` | `account_id`, `chat_id`, `max_id`, `outbox`, `unread` | `outbox: true` — собеседник прочитал ваши сообщения; `false` — чат прочитан в другом клиенте или панелью, `unread` — сколько осталось непрочитанным |
