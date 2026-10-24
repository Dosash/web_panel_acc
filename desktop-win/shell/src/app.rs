//! Программа: окна, режимы (свой сервер или веб-панель на вашем сервере), трей, выход, подключение.
//! Повторяет desktop/launcher.py + desktop/shell.py, но на Tauri 2 + WebView2.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::webview::NewWindowResponse;
use tauri::window::Color;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};

use crate::connection::{self, LOCAL, REMOTE};
use crate::server::{self, LocalServer};
use crate::settings::Settings;
use crate::tray::{self, Tray};
use crate::webview::{self, Kind};
use crate::{autostart, helper, logger, notify, paths, updater};
use paths::{APP_NAME, VERSION};

const ZOOM_STEPS: [f64; 11] = [0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0];
const UPDATE_PATH: &str = "/tg-desktop/update";
const MAIN: &str = "main";
const CONNECT: &str = "connect";
const DARK: Color = Color(11, 18, 32, 255);

pub struct Shell {
    pub data: PathBuf,
    pub log_path: PathBuf,
    start_hidden: bool,
    /// запуск после обновления помощником: с какой версии и когда начался выход прежней
    updated_from: Option<(String, u128)>,
    settings: Mutex<Settings>,
    mode: Mutex<String>,
    base: Mutex<Option<Url>>,
    server: Mutex<Option<Arc<LocalServer>>>,
    quitting: AtomicBool,
    ui: Mutex<Ui>,
    tray: Mutex<Option<Tray>>,
    downloads: AtomicU32,
}

#[derive(Default)]
struct Ui {
    last_blur: Option<Instant>,
    hidden_since: Option<Instant>,
    /// показан свой экран вместо панели (ожидание сервера, ошибка)
    status: bool,
    retrying: bool,
    viewers: u32,
    zoom: f64,
    /// плашка, которую нужно вернуть после перезагрузки страницы
    banner: Option<Value>,
    /// первый запуск: окно подключения открыто до главного окна
    first_connect: bool,
    health_written: bool,
    tray_hint: bool,
    /// окно было развёрнуто на весь экран — развернуть при первом показе
    maximize_on_show: bool,
}

static SHELL: OnceLock<Shell> = OnceLock::new();

pub fn shell() -> &'static Shell {
    SHELL.get().expect("программа не инициализирована")
}

fn ui<T>(f: impl FnOnce(&mut Ui) -> T) -> T {
    f(&mut shell().ui.lock().unwrap_or_else(|e| e.into_inner()))
}

fn settings<T>(f: impl FnOnce(&mut Settings) -> T) -> T {
    f(&mut shell().settings.lock().unwrap_or_else(|e| e.into_inner()))
}

pub fn setting(key: &str) -> Option<String> {
    settings(|s| s.get(key))
}

pub fn set_setting(key: &str, value: &str) {
    settings(|s| {
        s.set(key, value);
        s.save();
    });
}

pub fn mode() -> String {
    shell().mode.lock().unwrap_or_else(|e| e.into_inner()).clone()
}

pub fn server_url() -> Option<String> {
    setting("server_url")
}

pub fn quitting() -> bool {
    SHELL.get().is_some_and(|s| s.quitting.load(Ordering::SeqCst))
}

pub fn auto_update() -> bool {
    settings(|s| s.get_bool("auto_update", true))
}

pub fn set_auto_update(on: bool) {
    set_setting("auto_update", if on { "true" } else { "false" });
}

pub fn with_tray(f: impl FnOnce(&Tray)) {
    if let Some(t) = shell().tray.lock().unwrap_or_else(|e| e.into_inner()).as_ref() {
        f(t);
    }
}

pub fn set_update_text(text: &str) {
    with_tray(|t| {
        let _ = t.update.set_text(text);
    });
}

// ---------- запуск ----------

pub struct Args {
    pub hidden: bool,
    pub updated_from: Option<(String, u128)>,
}

pub fn run(args: Args) {
    let data = paths::data_dir();
    let _ = std::fs::create_dir_all(&data);
    let log_path = logger::init(&data);
    log::info!("TG Panel {VERSION} для Windows (Tauri, WebView2 {}): данные {}",
        webview::runtime_version().unwrap_or_else(|| "нет".into()), data.display());
    if webview::runtime_version().is_none() {
        let open = rfd::MessageDialog::new()
            .set_title(APP_NAME)
            .set_level(rfd::MessageLevel::Error)
            .set_description("Для работы TG Panel нужен Microsoft Edge WebView2 Runtime — его нет на этом компьютере.\n\nОткрыть страницу загрузки?")
            .set_buttons(rfd::MessageButtons::YesNo)
            .show();
        if open == rfd::MessageDialogResult::Yes {
            shell_open("https://developer.microsoft.com/microsoft-edge/webview2/#download");
        }
        return;
    }
    notify::register(&data);
    autostart::repair();

    // одна копия на папку данных: вторая только показывает окно первой (плагин single-instance ниже).
    // Скачанное в прошлый раз обновление ставим, только если других копий нет
    let first_copy = single_marker(&data);
    let settings = Settings::load(&data.join("desktop.ini"));
    if first_copy && args.updated_from.is_none() && settings.get_bool("auto_update", true)
        && updater::install_pending_at_start(&data, args.hidden)
    {
        return;
    }

    let mode = settings.get("mode").filter(|m| m == LOCAL || m == REMOTE).unwrap_or_default();
    let zoom = snap_zoom(settings.get_f64("zoom").unwrap_or(1.0));
    let _ = SHELL.set(Shell {
        data: data.clone(),
        log_path,
        start_hidden: args.hidden,
        updated_from: args.updated_from,
        settings: Mutex::new(settings),
        mode: Mutex::new(mode),
        base: Mutex::new(None),
        server: Mutex::new(None),
        quitting: AtomicBool::new(false),
        ui: Mutex::new(Ui { zoom, ..Default::default() }),
        tray: Mutex::new(None),
        downloads: AtomicU32::new(0),
    });

    let mut context = tauri::generate_context!();
    // одна копия на папку данных (переносная версия и обычная — разные программы)
    context.config_mut().identifier = format!("TGPanel.Desktop.{}", paths::data_tag(&data));
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            log::info!("Повторный запуск — показываем уже открытое окно");
            show_main(app);
        }))
        .setup(|app| {
            setup(app.handle());
            Ok(())
        })
        .on_window_event(on_window_event)
        .build(context);
    let app = match app {
        Ok(app) => app,
        Err(e) => {
            log::error!("Не удалось запустить окно: {e}");
            return;
        }
    };
    app.run(|app, event| match event {
        // окна не закрываются, а прячутся в трей; выход — только через quit()
        RunEvent::ExitRequested { code: None, api, .. } if !quitting() => api.prevent_exit(),
        RunEvent::Exit => {
            if let Some(server) = shell().server.lock().unwrap_or_else(|e| e.into_inner()).take() {
                server.stop(server::STOP_TIMEOUT);
            }
            let _ = app;
        }
        _ => {}
    });
}

/// Именованный объект «копия для этой папки данных уже запущена» — до плагина single-instance,
/// чтобы вторая копия не взялась ставить обновление под работающей первой.
fn single_marker(data: &Path) -> bool {
    use windows::core::HSTRING;
    use windows::Win32::Foundation::{GetLastError, ERROR_ALREADY_EXISTS};
    use windows::Win32::System::Threading::CreateMutexW;
    let name = HSTRING::from(format!("TGPanel.Desktop.{}.running", paths::data_tag(data)));
    unsafe {
        // хэндл не закрываем: объект живёт, пока жив процесс
        let _handle = CreateMutexW(None, false, &name);
        GetLastError() != ERROR_ALREADY_EXISTS
    }
}

fn setup(app: &AppHandle) {
    match tray::build(app) {
        Ok(t) => *shell().tray.lock().unwrap_or_else(|e| e.into_inner()) = Some(t),
        Err(e) => log::error!("Не удалось создать значок в трее: {e}"),
    }
    if mode().is_empty() {
        // TG_PANEL_SERVER=http://…/accounts/ — при первом запуске сразу свой сервер, без вопроса
        let preset = std::env::var("TG_PANEL_SERVER").unwrap_or_default();
        if !preset.trim().is_empty() {
            let url = connection::normalize_url(&preset);
            log::info!("Режим сервера из TG_PANEL_SERVER: {url}");
            save_connection(REMOTE, &url);
        } else {
            open_connect(app, true);
            return;
        }
    }
    start_main(app);
}

fn save_connection(mode: &str, url: &str) {
    settings(|s| {
        s.set("mode", mode);
        if !url.is_empty() {
            s.set("server_url", url);
        }
        s.save();
    });
    *shell().mode.lock().unwrap_or_else(|e| e.into_inner()) = mode.to_string();
    with_tray(|t| {
        let _ = t.connection.set_text(tray::connection_text());
    });
}

fn page_script() -> String {
    let info = json!({"version": VERSION, "mode": mode(), "hideLogout": mode() == LOCAL});
    include_str!("page.js").replace("__TG_APP__", &info.to_string())
}

fn webview_dir() -> PathBuf {
    // профиль WebView2 (cookie, localStorage, кэш) — свой; прежний webengine (Qt) не трогаем
    shell().data.join("webview2")
}

fn start_main(app: &AppHandle) {
    let remote = mode() == REMOTE;
    let start = if remote {
        let url = server_url().and_then(|u| Url::parse(&u).ok());
        *shell().base.lock().unwrap_or_else(|e| e.into_inner()) = url.clone();
        url
    } else {
        None
    };
    log::info!("Режим: {}", if remote { format!("сервер {}", server_url().unwrap_or_default()) } else { "на этом компьютере".into() });
    let window = match create_main(app, start.clone()) {
        Ok(w) => w,
        Err(e) => {
            log::error!("Не удалось создать окно: {e}");
            quit(app, After::Nothing);
            return;
        }
    };
    if start.is_none() {
        if remote {
            show_status(&window, "Адрес сервера не задан", "Укажите его: значок в трее → «Подключение…»", false,
                &[("connection", "Подключение…", true)]);
        } else {
            show_status(&window, "Запуск…", "Подключаем аккаунты", true, &[]);
            start_server(app);
        }
    }
    if remote {
        // в режиме сервера своя часть — только окно: оно создано, значит новая версия работает
        let app = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(5));
            mark_healthy(&app);
        });
    }
    updater::start(app);
    after_update_notice(app);
}

fn create_main(app: &AppHandle, url: Option<Url>) -> tauri::Result<WebviewWindow> {
    let target = url.map(WebviewUrl::External).unwrap_or_else(|| WebviewUrl::External("about:blank".parse().unwrap()));
    let window = viewer_builder(app, MAIN, target)
        .inner_size(1280.0, 820.0)
        .center()
        .background_color(DARK)
        .build()?;
    let maximized = setting("window").is_some_and(|p| crate::placement::restore(&window, &p));
    ui(|u| u.maximize_on_show = maximized);
    webview::attach(&window, Kind::Main);
    let _ = window.set_zoom(ui(|u| u.zoom));
    if shell().start_hidden {
        ui(|u| u.hidden_since = Some(Instant::now()));
        log::info!("Запуск в трее (--hidden)");
    } else {
        show_main(app);
    }
    Ok(window)
}

/// Общие настройки для окон с панелью (главное, фото/видео, бот).
fn viewer_builder<'a>(app: &'a AppHandle, label: &str, url: WebviewUrl) -> WebviewWindowBuilder<'a, tauri::Wry, AppHandle> {
    let (nav, popup) = (app.clone(), app.clone());
    let label_ = label.to_string();
    WebviewWindowBuilder::new(app, label, url)
        .title(APP_NAME)
        .min_inner_size(380.0, 480.0)
        .visible(false)
        .data_directory(webview_dir())
        .initialization_script(page_script())
        .zoom_hotkeys_enabled(true)
        // HTML5 drag & drop (файлы в чат) — странице, а не Tauri
        .disable_drag_drop_handler()
        .on_navigation(move |url| allow_navigation(&nav, &label_, url))
        .on_new_window(move |url, _| {
            open_url(&popup, &url, true);
            NewWindowResponse::Deny
        })
}

fn base() -> Option<Url> {
    shell().base.lock().unwrap_or_else(|e| e.into_inner()).clone()
}

/// Адрес своей панели: тот же origin и путь под путём панели (на сервере за nginx рядом другие панели).
pub fn is_panel_url(url: &Url) -> bool {
    let Some(base) = base() else { return false };
    url.scheme() == base.scheme()
        && url.host_str() == base.host_str()
        && url.port_or_known_default() == base.port_or_known_default()
        && url.path().starts_with(base.path())
}

fn allow_navigation(app: &AppHandle, label: &str, url: &Url) -> bool {
    if matches!(url.scheme(), "data" | "about" | "blob") || url.host_str() == Some("tauri.localhost") {
        return true;
    }
    if is_panel_url(url) {
        if label == MAIN && url.path().ends_with(UPDATE_PATH) {
            // «Обновить программу» в окне обновления панели
            updater::check(app, true);
            return false;
        }
        return true;
    }
    open_url(app, url, false);
    false
}

/// Адреса панели «в новом окне» — отдельное окно программы, всё остальное — системный браузер
/// (tg:// — Telegram, mailto: — почта).
fn open_url(app: &AppHandle, url: &Url, popup: bool) {
    if is_panel_url(url) {
        if popup {
            open_viewer(app, url);
        }
        return;
    }
    if matches!(url.scheme(), "http" | "https" | "tg" | "mailto" | "tel") {
        shell_open(url.as_str());
    }
}

fn open_viewer(app: &AppHandle, url: &Url) {
    // панель встроенного бота (<панель>/bots/<имя>/) — одно окно на бота: повторно поднимаем открытое
    let base_path = base().map(|b| b.path().trim_end_matches('/').to_string()).unwrap_or_default();
    let rest = url.path().strip_prefix(&base_path).unwrap_or("");
    let bot = rest.strip_prefix("/bots/").and_then(|r| r.split('/').next()).filter(|b| !b.is_empty() && rest.matches('/').count() >= 3);
    let label = match bot {
        Some(bot) => {
            let label = format!("bot-{}", bot.chars().filter(|c| c.is_ascii_alphanumeric()).collect::<String>());
            if let Some(w) = app.get_webview_window(&label) {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
                return;
            }
            label
        }
        None => format!("viewer-{}", ui(|u| {
            u.viewers += 1;
            u.viewers
        })),
    };
    let (w, h) = if bot.is_some() { (1280.0, 860.0) } else { (1000.0, 760.0) };
    let title_label = label.clone();
    let built = viewer_builder(app, &label, WebviewUrl::External(url.clone()))
        .inner_size(w, h)
        .center()
        .background_color(if bot.is_some() { DARK } else { Color(0, 0, 0, 255) })
        .on_document_title_changed(move |w, title| {
            let _ = w.set_title(&if title.is_empty() || title.starts_with("http") { APP_NAME.to_string() } else { format!("{title} — {APP_NAME}") });
            let _ = &title_label;
        })
        .build();
    match built {
        Ok(window) => {
            webview::attach(&window, if bot.is_some() { Kind::Bot } else { Kind::Media });
            let _ = window.show();
            let _ = window.set_focus();
        }
        Err(e) => log::error!("Не удалось открыть окно {url}: {e}"),
    }
}

// ---------- свой сервер (режим «на этом компьютере») ----------

fn start_server(app: &AppHandle) {
    let port = settings(|s| s.get_u16("port")).unwrap_or(0);
    let events = app.clone();
    let started = LocalServer::start(&shell().data, port, move |event| {
        let app = events.clone();
        let _ = events.run_on_main_thread(move || on_server_event(&app, event));
    });
    match started {
        Ok(server) => *shell().server.lock().unwrap_or_else(|e| e.into_inner()) = Some(Arc::new(server)),
        Err(e) => {
            log::error!("Серверная часть не запустилась: {e}");
            server_failed(app, "Не удалось запустить панель", &format!("{e}\n{}", paths::server_command()[0].display()));
        }
    }
}

fn on_server_event(app: &AppHandle, event: server::Event) {
    if quitting() {
        return;
    }
    let Some(window) = app.get_webview_window(MAIN) else { return };
    match event {
        server::Event::Ready { port, cookie } => {
            set_setting("port", &port.to_string());
            let url: Url = format!("http://127.0.0.1:{port}/").parse().expect("адрес");
            *shell().base.lock().unwrap_or_else(|e| e.into_inner()) = Some(url.clone());
            webview::login_and_open(&window, url, cookie.0, cookie.1);
            mark_healthy(app);
        }
        server::Event::Error(msg) => server_failed(app, "Не удалось запустить панель", &msg),
        server::Event::Exited(code) => {
            *shell().server.lock().unwrap_or_else(|e| e.into_inner()) = None;
            server_failed(app, "Сервер панели остановился", &format!("Код выхода: {}", code.map_or("—".into(), |c| c.to_string())));
        }
    }
}

fn server_failed(app: &AppHandle, title: &str, text: &str) {
    if shell().updated_from.is_some() && !ui(|u| u.health_written) {
        // новая версия после обновления не подняла сервер — помощник вернёт прежнюю
        write_health(&format!("fail: {title}: {text}"));
        log::error!("{title}: {text} — возвращаем прежнюю версию");
        quit(app, After::Nothing);
        return;
    }
    if let Some(window) = app.get_webview_window(MAIN) {
        let text = format!("{text}\n\nПодробности в журнале:\n{}", shell().log_path.display());
        show_status(&window, title, &text, false,
            &[("restart-server", "Перезапустить", true), ("log", "Открыть журнал", false), ("connection", "Подключение…", false)]);
        show_main(app);
    }
}

fn write_health(text: &str) {
    if ui(|u| std::mem::replace(&mut u.health_written, true)) {
        return;
    }
    let _ = std::fs::write(helper::health_path(&shell().data, VERSION), text);
}

/// Новая версия после обновления поднялась (окно и сервер) — помощнику можно не откатывать.
fn mark_healthy(app: &AppHandle) {
    let Some((from, stop_started)) = shell().updated_from.clone() else { return };
    if ui(|u| u.health_written) {
        return;
    }
    write_health("ok");
    let downtime = (helper::now_ms().saturating_sub(stop_started)) as f64 / 1000.0;
    log::info!("Обновление {from} → {VERSION}: программа снова работает, простой {downtime:.1} с");
    let _ = app;
}

// ---------- свои экраны ----------

fn show_status(window: &WebviewWindow, title: &str, text: &str, spinner: bool, actions: &[(&str, &str, bool)]) {
    if window.label() == MAIN {
        ui(|u| u.status = true);
    }
    let status = json!({"title": title, "text": text, "spinner": spinner, "actions": actions});
    let html = include_str!("../ui/status.html").replace("__STATUS__", &status.to_string().replace("</", "<\\/"));
    webview::show_html(window, html);
}

fn show_remote_down(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else { return };
    let url = server_url().unwrap_or_default();
    show_status(&window, "Сервер панели недоступен",
        &format!("{url}\nПовторяем подключение каждые 10 секунд…\n\nСменить адрес — значок в трее → «Подключение…»"),
        true, &[("retry", "Повторить сейчас", true), ("connection", "Подключение…", false)]);
    if ui(|u| std::mem::replace(&mut u.retrying, true)) {
        return;
    }
    // сервер недоступен (выключен, нет сети) — проверяем в фоне и открываем панель, когда ответит
    let app = app.clone();
    std::thread::spawn(move || loop {
        std::thread::sleep(Duration::from_secs(10));
        if quitting() || !ui(|u| u.status) || mode() != REMOTE {
            ui(|u| u.retrying = false);
            return;
        }
        if connection::check_server(&url).is_none() {
            ui(|u| u.retrying = false);
            log::info!("Сервер панели снова отвечает");
            let app2 = app.clone();
            let _ = app.run_on_main_thread(move || open_panel(&app2));
            return;
        }
    });
}

fn open_panel(app: &AppHandle) {
    if let (Some(window), Some(url)) = (app.get_webview_window(MAIN), base()) {
        let _ = window.navigate(url);
    }
}

pub fn on_navigation_completed(app: &AppHandle, source: &str, ok: bool, status: i32, http: i32) {
    let Ok(url) = Url::parse(source) else { return };
    if !is_panel_url(&url) {
        return;
    }
    let gateway_down = matches!(http, 502..=504);
    if (!ok || gateway_down) && mode() == REMOTE {
        log::warn!("Панель не загрузилась: {source} (ошибка {status}, HTTP {http})");
        show_remote_down(app);
        return;
    }
    if !ok {
        return;
    }
    ui(|u| u.status = false);
    set_active(app);
    if let Some(banner) = ui(|u| u.banner.clone()) {
        eval_main(app, &format!("window.__tgDesktopBanner({banner})"));
    }
}

fn eval_main(app: &AppHandle, js: &str) {
    if let Some(w) = app.get_webview_window(MAIN) {
        let _ = w.eval(js);
    }
}

pub fn on_page_message(app: &AppHandle, label: &str, source: &str, msg: &Value) {
    let kind = msg["type"].as_str().unwrap_or_default();
    let from_panel = Url::parse(source).is_ok_and(|u| is_panel_url(&u));
    // свои экраны открыты через NavigateToString: адрес — about:blank или data:
    let from_own = source.starts_with("about:") || source.starts_with("data:");
    match kind {
        "notify" if from_panel => {
            let title = msg["title"].as_str().unwrap_or(APP_NAME);
            notify(app, title, msg["body"].as_str().unwrap_or_default());
            if let Some(w) = app.get_webview_window(MAIN) {
                let _ = w.request_user_attention(Some(tauri::UserAttentionType::Informational));
            }
        }
        "js-error" if from_panel => log::warn!("js: {}", msg["text"].as_str().unwrap_or_default()),
        "banner" if from_panel => {
            ui(|u| u.banner = None);
            if msg["id"] == "update" && msg["action"] == "action" {
                updater::install_now(app);
            }
        }
        "status" if from_own && label == MAIN => match msg["action"].as_str().unwrap_or_default() {
            "retry" => open_panel(app),
            "connection" => open_connect(app, false),
            "log" => shell_open(&shell().log_path.to_string_lossy()),
            "restart-server" => {
                if let Some(w) = app.get_webview_window(MAIN) {
                    show_status(&w, "Запуск…", "Подключаем аккаунты", true, &[]);
                }
                if let Some(old) = shell().server.lock().unwrap_or_else(|e| e.into_inner()).take() {
                    old.stop(server::STOP_TIMEOUT);
                }
                start_server(app);
            }
            _ => {}
        },
        "connect" if from_own && label == CONNECT => connect_submit(app, msg),
        "connect-cancel" if label == CONNECT => connect_cancel(app),
        _ => {}
    }
}

// ---------- окно и трей ----------

pub fn main_visible() -> bool {
    SHELL.get().is_some() && ui(|u| u.hidden_since.is_none())
}

pub fn hidden_for() -> Option<Duration> {
    ui(|u| u.hidden_since.map(|t| t.elapsed()))
}

pub fn show_main(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else {
        if let Some(w) = app.get_webview_window(CONNECT) {
            let _ = w.show();
            let _ = w.set_focus();
        }
        return;
    };
    let _ = window.unminimize();
    if ui(|u| std::mem::take(&mut u.maximize_on_show)) {
        let _ = window.maximize();
    }
    let _ = window.show();
    let _ = window.set_focus();
    ui(|u| u.hidden_since = None);
    set_active(app);
}

fn hide_main(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else { return };
    save_placement(&window);
    let _ = window.hide();
    ui(|u| u.hidden_since = Some(Instant::now()));
    set_active(app);
}

/// Щелчок по значку в трее: окно на виду — спрятать, иначе показать. Щелчок по трею сам забирает фокус у окна,
/// поэтому «на виду» — это ещё и «потеряло фокус только что».
pub fn toggle_main(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else {
        show_main(app);
        return;
    };
    let visible = window.is_visible().unwrap_or(false) && !window.is_minimized().unwrap_or(false);
    let focused = window.is_focused().unwrap_or(false) || ui(|u| u.last_blur.is_some_and(|t| t.elapsed() < Duration::from_millis(400)));
    if visible && focused {
        hide_main(app);
    } else {
        show_main(app);
    }
}

/// Для страницы окно «активно», только если оно на виду и в фокусе (уведомления — когда не активно).
fn set_active(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN) else { return };
    let active = window.is_visible().unwrap_or(false) && !window.is_minimized().unwrap_or(false) && window.is_focused().unwrap_or(false);
    let _ = window.eval(format!("window.__tgDesktopActive = {active};"));
}

fn save_placement(window: &WebviewWindow) {
    if let Some(p) = crate::placement::save(window) {
        set_setting("window", &p);
    }
}

fn on_window_event(window: &tauri::Window, event: &WindowEvent) {
    let app = window.app_handle();
    let label = window.label();
    match event {
        WindowEvent::CloseRequested { api, .. } if label == MAIN && !quitting() => {
            // как Telegram: окно закрывается, аккаунты остаются на связи и присылают уведомления
            api.prevent_close();
            hide_main(app);
            let shown = settings(|s| s.get_bool("tray_hint_shown", false)) || ui(|u| std::mem::replace(&mut u.tray_hint, true));
            if !shown {
                set_setting("tray_hint_shown", "true");
                notify(app, APP_NAME, "Панель работает в фоне. Открыть или выйти — через значок в трее.");
            }
        }
        WindowEvent::CloseRequested { api, .. } if label == CONNECT && ui(|u| u.first_connect) => {
            api.prevent_close();
            connect_cancel(app);
        }
        WindowEvent::Focused(focused) if label == MAIN => {
            if !focused {
                ui(|u| u.last_blur = Some(Instant::now()));
            }
            set_active(app);
        }
        WindowEvent::Resized(_) if label == MAIN => set_active(app),
        _ => {}
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Key {
    Reload,
    Fullscreen,
    DevTools,
    Quit,
    ZoomIn,
    ZoomOut,
    ZoomReset,
    Close,
}

pub fn on_key(app: &AppHandle, label: &str, key: Key) {
    let Some(window) = app.get_webview_window(label) else { return };
    match key {
        Key::Reload => reload(app, label),
        Key::Fullscreen => {
            let full = window.is_fullscreen().unwrap_or(false);
            let _ = window.set_fullscreen(!full);
        }
        Key::DevTools => window.open_devtools(),
        Key::Quit => quit(app, After::Nothing),
        Key::ZoomIn => zoom(app, 1),
        Key::ZoomOut => zoom(app, -1),
        Key::ZoomReset => zoom(app, 0),
        Key::Close => {
            let _ = window.close();
        }
    }
}

pub fn reload(app: &AppHandle, label: &str) {
    if label == MAIN && ui(|u| u.status) {
        // на своём экране «обновить» — значит попробовать панель снова
        if base().is_some() {
            open_panel(app);
        }
        return;
    }
    if let Some(window) = app.get_webview_window(label) {
        webview::reload(&window);
    }
}

pub fn on_browser_crash(app: &AppHandle, label: &str) {
    // процесс WebView2 целиком — окно больше не оживить; главное окно пересоздаёт перезапуск программы
    if label == MAIN && !quitting() {
        log::error!("WebView2 завершился — перезапускаем программу");
        quit(app, After::Restart);
    }
}

// ---------- масштаб ----------

pub fn snap_zoom(factor: f64) -> f64 {
    let factor = factor.clamp(ZOOM_STEPS[0], ZOOM_STEPS[ZOOM_STEPS.len() - 1]);
    ZOOM_STEPS.iter().copied().min_by(|a, b| (a - factor).abs().total_cmp(&(b - factor).abs())).unwrap_or(1.0)
}

pub fn current_zoom() -> f64 {
    ui(|u| u.zoom)
}

fn zoom(app: &AppHandle, direction: i32) {
    let current = current_zoom();
    let value = match direction {
        0 => 1.0,
        d if d > 0 => ZOOM_STEPS.iter().copied().find(|z| *z > current + 0.01).unwrap_or(ZOOM_STEPS[ZOOM_STEPS.len() - 1]),
        _ => ZOOM_STEPS.iter().rev().copied().find(|z| *z < current - 0.01).unwrap_or(ZOOM_STEPS[0]),
    };
    if let Some(w) = app.get_webview_window(MAIN) {
        let _ = w.set_zoom(value);
    }
    zoom_changed(app, value);
}

pub fn zoom_changed(_app: &AppHandle, factor: f64) {
    let factor = snap_zoom(factor);
    if (ui(|u| std::mem::replace(&mut u.zoom, factor)) - factor).abs() > 0.001 {
        set_setting("zoom", &format!("{factor}"));
    }
}

// ---------- уведомления, диалоги, файлы ----------

pub fn notify(app: &AppHandle, title: &str, body: &str) {
    notify::show(app, title, body);
}

fn main_or_any(app: &AppHandle) -> Option<WebviewWindow> {
    app.get_webview_window(MAIN).or_else(|| app.get_webview_window(CONNECT))
}

/// Сообщение (в отдельном потоке — диалог модальный и не держит цикл событий).
pub fn message(app: &AppHandle, text: &str) {
    let (window, text) = (main_or_any(app), text.to_string());
    std::thread::spawn(move || {
        let mut dialog = rfd::MessageDialog::new().set_title(APP_NAME).set_description(text).set_buttons(rfd::MessageButtons::Ok);
        if let Some(w) = window.as_ref().filter(|w| w.is_visible().unwrap_or(false)) {
            dialog = dialog.set_parent(w);
        }
        dialog.show();
    });
}

/// Вопрос «Да/Нет» поверх окна. Блокирует вызывающий поток — только не из главного.
pub fn ask(window: &WebviewWindow, text: &str) -> bool {
    rfd::MessageDialog::new()
        .set_title(APP_NAME)
        .set_description(text)
        .set_buttons(rfd::MessageButtons::YesNo)
        .set_parent(window)
        .show()
        == rfd::MessageDialogResult::Yes
}

pub fn ask_main(app: &AppHandle, text: &str) -> bool {
    let mut dialog = rfd::MessageDialog::new().set_title(APP_NAME).set_description(text).set_buttons(rfd::MessageButtons::YesNo);
    if let Some(w) = main_or_any(app).filter(|w| w.is_visible().unwrap_or(false)) {
        dialog = dialog.set_parent(&w);
    }
    dialog.show() == rfd::MessageDialogResult::Yes
}

pub fn ask_custom(app: &AppHandle, text: &str, yes: &str, no: &str) -> bool {
    let mut dialog = rfd::MessageDialog::new()
        .set_title(APP_NAME)
        .set_description(text)
        .set_buttons(rfd::MessageButtons::OkCancelCustom(yes.to_string(), no.to_string()));
    if let Some(w) = main_or_any(app).filter(|w| w.is_visible().unwrap_or(false)) {
        dialog = dialog.set_parent(&w);
    }
    match dialog.show() {
        rfd::MessageDialogResult::Ok | rfd::MessageDialogResult::Yes => true,
        rfd::MessageDialogResult::Custom(label) => label == yes,
        _ => false,
    }
}

pub fn download_dir() -> Option<PathBuf> {
    setting("download_dir").map(PathBuf::from).filter(|p| p.is_dir())
}

pub fn set_download_dir(path: &Path) {
    if let Some(dir) = path.parent() {
        set_setting("download_dir", &dir.to_string_lossy());
    }
}

pub fn download_started() {
    shell().downloads.fetch_add(1, Ordering::SeqCst);
}

pub fn downloads_active() -> bool {
    shell().downloads.load(Ordering::SeqCst) > 0
}

/// error: None — сохранён, Some("") — отменён, Some(текст) — ошибка.
pub fn download_finished(app: &AppHandle, path: &Path, error: Option<String>) {
    shell().downloads.fetch_sub(1, Ordering::SeqCst);
    match error {
        None => {
            log::info!("Файл сохранён: {}", path.display());
            notify(app, "Файл сохранён", &path.to_string_lossy());
        }
        Some(e) if e.is_empty() => {}
        Some(e) => {
            log::warn!("Файл не сохранён ({}): {e}", path.display());
            message(app, &format!("Не удалось сохранить файл:\n{e}"));
        }
    }
}

/// Открыть адрес или папку системой (браузер, Telegram, проводник).
pub fn shell_open(target: &str) {
    use windows::core::HSTRING;
    use windows::Win32::UI::Shell::ShellExecuteW;
    use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
    unsafe {
        ShellExecuteW(None, &HSTRING::from("open"), &HSTRING::from(target), None, None, SW_SHOWNORMAL);
    }
}

// ---------- обновление: плашка в окне и «Обновлено до» ----------

pub fn show_update_banner(app: &AppHandle, version: &str) {
    let banner = json!({"id": "update", "title": format!("Обновление готово · TG Panel {version}"),
        "text": "Перезапуск займёт несколько секунд, аккаунты переподключатся сами.", "action": "Перезапустить"});
    ui(|u| u.banner = Some(banner.clone()));
    let app = app.clone();
    let _ = app.clone().run_on_main_thread(move || eval_main(&app, &format!("window.__tgDesktopBanner({banner})")));
}

/// Один раз после обновления: «Обновлено до X» с кратким описанием из CHANGELOG.md (описание релиза).
fn after_update_notice(app: &AppHandle) {
    let data = &shell().data;
    let last = setting("last_version");
    set_setting("last_version", VERSION);
    let state = updater::load_state(data);
    if let Some(rb) = state.get("rolled_back").filter(|v| v.is_object()) {
        if rb["to"] == VERSION {
            notify(app, "Обновление не установилось",
                &format!("TG Panel {} не запустилась — возвращена версия {VERSION}. Подробности в журнале.", rb["version"].as_str().unwrap_or("?")));
        }
        updater::update_state(data, |s| {
            s.remove("rolled_back");
        });
    }
    // прежняя версия: из --updated-from, из last_version или программа на PyQt5 (настройки есть, last_version нет)
    let upgraded = shell().updated_from.is_some()
        || last.as_deref().is_some_and(|l| paths::newer(VERSION, l))
        || (last.is_none() && setting("mode").is_some() && ui(|u| !u.first_connect));
    if !upgraded {
        return;
    }
    let notes = state["pending"]["notes"].as_str().filter(|_| state["pending"]["version"] == VERSION).unwrap_or_default();
    let text = short_notes(notes);
    let banner = json!({"id": "updated", "title": format!("Обновлено до TG Panel {VERSION}"), "text": text, "timeout": 25000});
    log::info!("Программа обновлена до {VERSION}");
    if main_visible() {
        ui(|u| u.banner = Some(banner));
    } else {
        notify(app, &format!("Обновлено до TG Panel {VERSION}"), if text.is_empty() { "Программа обновлена" } else { &text });
    }
}

/// Первые пункты раздела CHANGELOG без разметки Markdown.
fn short_notes(md: &str) -> String {
    md.lines()
        .filter_map(|l| l.trim_start().strip_prefix("- "))
        .take(3)
        .map(|l| {
            let plain = l.replace("**", "").replace('`', "");
            let mut s: String = plain.chars().take(110).collect();
            if plain.chars().count() > 110 {
                s.push('…');
            }
            format!("• {s}")
        })
        .collect::<Vec<_>>()
        .join("\n")
}

// ---------- подключение ----------

pub fn open_connect(app: &AppHandle, first: bool) {
    if let Some(w) = app.get_webview_window(CONNECT) {
        let _ = w.show();
        let _ = w.set_focus();
        return;
    }
    ui(|u| u.first_connect = first);
    let current = json!({"mode": if mode().is_empty() { LOCAL.to_string() } else { mode() }, "url": server_url().unwrap_or_default()});
    let html = include_str!("../ui/connect.html").replace("__CONNECT__", &current.to_string().replace("</", "<\\/"));
    let window = WebviewWindowBuilder::new(app, CONNECT, WebviewUrl::External("about:blank".parse().unwrap()))
        .title(format!("{APP_NAME} — подключение"))
        .inner_size(560.0, 470.0)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .center()
        .visible(false)
        .data_directory(webview_dir())
        .background_color(DARK)
        .build();
    match window {
        Ok(window) => {
            webview::attach(&window, Kind::Connect);
            webview::show_html(&window, html);
            let _ = window.show();
            let _ = window.set_focus();
        }
        Err(e) => log::error!("Не удалось открыть окно подключения: {e}"),
    }
}

fn connect_reply(app: &AppHandle, error: &str, url: &str) {
    if let Some(w) = app.get_webview_window(CONNECT) {
        webview::post(&w, &json!({"type": "check", "error": error, "url": url}));
    }
}

fn connect_submit(app: &AppHandle, msg: &Value) {
    let new_mode = if msg["mode"] == REMOTE { REMOTE } else { LOCAL };
    if new_mode == LOCAL {
        connect_finish(app, LOCAL, String::new());
        return;
    }
    let url = connection::normalize_url(msg["url"].as_str().unwrap_or_default());
    let app = app.clone();
    std::thread::spawn(move || {
        let problem = connection::check_server(&url);
        let app2 = app.clone();
        let _ = app.run_on_main_thread(move || match problem {
            Some(problem) => connect_reply(&app2, &format!("{url}: {problem}"), &url),
            None => connect_finish(&app2, REMOTE, url),
        });
    });
}

fn connect_finish(app: &AppHandle, new_mode: &'static str, url: String) {
    if ui(|u| u.first_connect) {
        ui(|u| u.first_connect = false);
        save_connection(new_mode, &url);
        if let Some(w) = app.get_webview_window(CONNECT) {
            let _ = w.destroy();
        }
        start_main(app);
        return;
    }
    let same = new_mode == mode() && (new_mode == LOCAL || server_url().as_deref() == Some(url.as_str()));
    if same {
        if let Some(w) = app.get_webview_window(CONNECT) {
            let _ = w.close();
        }
        return;
    }
    let app = app.clone();
    std::thread::spawn(move || {
        if new_mode == LOCAL && mode() == REMOTE {
            let Some(w) = app.get_webview_window(CONNECT) else { return };
            let ok = ask(&w, "Аккаунты будут подключаться из этой программы. Не используйте одни и те же сессии \
                              одновременно здесь и на сервере — Telegram может их сбросить. Продолжить?");
            if !ok {
                connect_reply(&app, "", &url);
                return;
            }
        }
        log::info!("Смена подключения: {} → {new_mode} {url}", mode());
        save_connection(new_mode, &url);
        let app2 = app.clone();
        let _ = app.run_on_main_thread(move || quit(&app2, After::Restart));
    });
}

fn connect_cancel(app: &AppHandle) {
    if ui(|u| u.first_connect) {
        quit(app, After::Nothing);
    } else if let Some(w) = app.get_webview_window(CONNECT) {
        let _ = w.close();
    }
}

// ---------- выход ----------

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum After {
    Nothing,
    /// перезапуск (смена подключения): новая копия ждёт выхода этой
    Restart,
    Update { relaunch: bool, hidden: bool },
}

/// Выход: окна прячутся сразу, сервер останавливается штатно (аккаунты отключаются), потом — обновление
/// или перезапуск, если нужно. Скачанное обновление ставится и при обычном выходе.
pub fn quit(app: &AppHandle, after: After) {
    if shell().quitting.swap(true, Ordering::SeqCst) {
        return;
    }
    let stop_started = helper::now_ms();
    let hidden = !main_visible();
    if let Some(window) = app.get_webview_window(MAIN) {
        save_placement(&window);
        // закрыть WebSocket страницы, иначе сервер ждёт его до таймаута
        let _ = window.navigate("about:blank".parse().unwrap());
    }
    for (_, window) in app.webview_windows() {
        let _ = window.hide();
    }
    with_tray(|t| {
        let _ = t.icon.set_visible(false);
    });
    if shell().updated_from.is_some() {
        write_health("ok"); // пользователь вышел сам — это не падение новой версии
    }
    let app = app.clone();
    std::thread::spawn(move || {
        if let Some(server) = shell().server.lock().unwrap_or_else(|e| e.into_inner()).take() {
            server.stop(server::STOP_TIMEOUT);
        }
        let update = match after {
            After::Update { relaunch, hidden } => Some((relaunch, hidden)),
            // скачанное обновление ставится при выходе; при смене подключения — и программа запускается снова
            After::Restart if updater::has_ready() => Some((true, hidden)),
            After::Nothing if updater::has_ready() => Some((false, true)),
            _ => None,
        };
        let mut restarted = false;
        if let Some((relaunch, hidden)) = update {
            if let Some(plan) = updater::plan(&shell().data, relaunch, hidden, stop_started) {
                match helper::launch(&shell().data, &plan) {
                    Ok(()) => restarted = true,
                    Err(e) => log::error!("Обновление не запущено: {e}"),
                }
            }
        }
        if !restarted && (after == After::Restart || matches!(after, After::Update { relaunch: true, .. })) {
            let mut args = vec![std::ffi::OsString::from("--wait-pid"), std::process::id().to_string().into()];
            if hidden {
                args.push("--hidden".into());
            }
            if let Err(e) = helper::spawn_detached(&paths::exe(), &args) {
                log::error!("Не удалось перезапустить программу: {e}");
            }
        }
        log::info!("Выход");
        app.exit(0);
    });
}
