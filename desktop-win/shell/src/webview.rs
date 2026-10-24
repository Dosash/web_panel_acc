//! Всё, что окно делает с WebView2 напрямую (через webview2-com): клавиши, контекстное меню, разрешения,
//! загрузки, cookie входа, масштаб, падение процесса страницы, полноэкранное видео, сообщения от страницы.
//! Обработчики WebView2 вызываются в главном потоке; диалоги показываются в отдельном потоке с deferral,
//! чтобы не крутить вложенный цикл сообщений внутри события WebView2.

use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Manager, WebviewWindow};
use webview2_com::Microsoft::Web::WebView2::Win32::*;
use webview2_com::*;
use windows::core::{Interface, BOOL, HSTRING, PWSTR};
use windows::Win32::UI::Input::KeyboardAndMouse::{GetKeyState, VK_CONTROL, VK_MENU, VK_SHIFT};

use crate::app;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Main,
    /// файл панели «в новой вкладке» (фото, видео) — Esc закрывает
    Media,
    /// панель встроенного бота: у бота свои окна внутри страницы, Esc не закрывает
    Bot,
    Connect,
}

/// COM-объект WebView2 для передачи в главный поток (run_on_main_thread требует Send).
/// Используется только в главном потоке — там же, где создан.
struct MainThread<T>(T);
unsafe impl<T> Send for MainThread<T> {}

impl<T> MainThread<T> {
    /// Метод, а не разбор по полям: замыкание должно захватить обёртку целиком (иначе захватит поля без Send).
    fn take(self) -> T {
        self.0
    }
}

const MESSAGE_PREFIX: &str = "tg-desktop:";

/// Пункты стандартного меню, которых у программы быть не должно: у неё нет вкладок и истории.
const HIDDEN_MENU_ITEMS: &[&str] = &[
    "back", "forward", "saveAs", "print", "viewPageSource", "inspectElement", "createQrCode", "share",
    "webCapture", "screenshot", "openLinkInNewWindow", "saveLinkAs", "saveImageAs", "copyImageLocation",
    "openLinkInProfile",
];

pub fn attach(window: &WebviewWindow, kind: Kind) {
    let app = window.app_handle().clone();
    let label = window.label().to_string();
    let _ = window.with_webview(move |pw| {
        if let Err(e) = unsafe { attach_handlers(app, label, kind, pw.controller()) } {
            log::error!("Не удалось настроить WebView2: {e}");
        }
    });
}

fn take(p: PWSTR) -> String {
    take_pwstr(p)
}

unsafe fn attach_handlers(app: AppHandle, label: String, kind: Kind, controller: ICoreWebView2Controller) -> windows::core::Result<()> {
    let webview = controller.CoreWebView2()?;
    let mut token = 0i64;

    // ---------- клавиши: срабатывают и когда фокус во фрейме мини-приложения ----------
    {
        let (app, label) = (app.clone(), label.clone());
        controller.add_AcceleratorKeyPressed(
            &AcceleratorKeyPressedEventHandler::create(Box::new(move |_, args| {
                let Some(args) = args else { return Ok(()) };
                let mut event = COREWEBVIEW2_KEY_EVENT_KIND::default();
                args.KeyEventKind(&mut event)?;
                if event != COREWEBVIEW2_KEY_EVENT_KIND_KEY_DOWN && event != COREWEBVIEW2_KEY_EVENT_KIND_SYSTEM_KEY_DOWN {
                    return Ok(());
                }
                let mut vk = 0u32;
                args.VirtualKey(&mut vk)?;
                let mut status = COREWEBVIEW2_PHYSICAL_KEY_STATUS::default();
                args.PhysicalKeyStatus(&mut status)?;
                let repeat = status.WasKeyDown.as_bool();
                let down = |k: u16| GetKeyState(k as i32) < 0;
                let (ctrl, shift, alt) = (down(VK_CONTROL.0), down(VK_SHIFT.0), down(VK_MENU.0));                if let Some(action) = key_action(kind, vk, ctrl, shift, alt) {
                    args.SetHandled(true)?;
                    if !repeat || matches!(action, app::Key::ZoomIn | app::Key::ZoomOut) {
                        let (app_, label) = (app.clone(), label.clone());
                        let _ = app.run_on_main_thread(move || app::on_key(&app_, &label, action));
                    }
                }
                Ok(())
            })),
            &mut token,
        )?;
    }

    if kind == Kind::Connect {
        attach_messages(&app, &label, &webview)?;
        return Ok(());
    }

    // ---------- контекстное меню без «Назад/Вперёд/Исходный код/Сохранить страницу» ----------
    if let Ok(webview11) = webview.cast::<ICoreWebView2_11>() {
        webview11.add_ContextMenuRequested(
            &ContextMenuRequestedEventHandler::create(Box::new(|_, args| {
                let Some(args) = args else { return Ok(()) };
                let items = args.MenuItems()?;
                let mut count = 0u32;
                items.Count(&mut count)?;
                let mut prev_separator = true;
                let mut i = 0u32;
                while i < count {
                    let item = items.GetValueAtIndex(i)?;
                    let mut name = PWSTR::null();
                    item.Name(&mut name)?;
                    let name = take(name);
                    let mut item_kind = COREWEBVIEW2_CONTEXT_MENU_ITEM_KIND::default();
                    item.Kind(&mut item_kind)?;
                    let separator = item_kind == COREWEBVIEW2_CONTEXT_MENU_ITEM_KIND_SEPARATOR;
                    // разделители в начале и подряд (после удалённых пунктов)
                    if HIDDEN_MENU_ITEMS.contains(&name.as_str()) || (separator && prev_separator) {
                        items.RemoveValueAtIndex(i)?;
                        count -= 1;
                        continue;
                    }
                    prev_separator = separator;
                    i += 1;
                }
                if count > 0 {
                    let last = items.GetValueAtIndex(count - 1)?;
                    let mut last_kind = COREWEBVIEW2_CONTEXT_MENU_ITEM_KIND::default();
                    last.Kind(&mut last_kind)?;
                    if last_kind == COREWEBVIEW2_CONTEXT_MENU_ITEM_KIND_SEPARATOR {
                        items.RemoveValueAtIndex(count - 1)?;
                    }
                }
                Ok(())
            })),
            &mut token,
        )?;
    }

    // ---------- разрешения: уведомления — всегда, камера/микрофон/геолокация — спросить ----------
    {
        let (app, label) = (app.clone(), label.clone());
        webview.add_PermissionRequested(
            &PermissionRequestedEventHandler::create(Box::new(move |_, args| {
                let Some(args) = args else { return Ok(()) };
                let mut permission = COREWEBVIEW2_PERMISSION_KIND::default();
                args.PermissionKind(&mut permission)?;
                let what = match permission {
                    COREWEBVIEW2_PERMISSION_KIND_NOTIFICATIONS | COREWEBVIEW2_PERMISSION_KIND_CLIPBOARD_READ => {
                        args.SetState(COREWEBVIEW2_PERMISSION_STATE_ALLOW)?;
                        return Ok(());
                    }
                    COREWEBVIEW2_PERMISSION_KIND_GEOLOCATION => "местоположению",
                    COREWEBVIEW2_PERMISSION_KIND_MICROPHONE => "микрофону",
                    COREWEBVIEW2_PERMISSION_KIND_CAMERA => "камере",
                    _ => return Ok(()),
                };
                let mut uri = PWSTR::null();
                args.Uri(&mut uri)?;
                let uri = take(uri);
                let host = url::Url::parse(&uri).ok().and_then(|u| u.host_str().map(str::to_string)).unwrap_or(uri);
                let deferral = args.GetDeferral()?;
                let pending = MainThread((args, deferral));
                let Some(window) = app.get_webview_window(&label) else { return Ok(()) };
                let app = app.clone();
                std::thread::spawn(move || {
                    let allowed = app::ask(&window, &format!("{host} просит доступ к {what}. Разрешить?"));
                    let _ = app.run_on_main_thread(move || {
                        let (args, deferral) = pending.take();
                        let state = if allowed { COREWEBVIEW2_PERMISSION_STATE_ALLOW } else { COREWEBVIEW2_PERMISSION_STATE_DENY };
                        unsafe {
                            let _ = args.SetState(state);
                            let _ = deferral.Complete();
                        }
                    });
                });
                Ok(())
            })),
            &mut token,
        )?;
    }

    // ---------- загрузки: «Сохранить как», последняя папка, уведомление по окончании ----------
    if let Ok(webview4) = webview.cast::<ICoreWebView2_4>() {
        let (app, label) = (app.clone(), label.clone());
        webview4.add_DownloadStarting(
            &DownloadStartingEventHandler::create(Box::new(move |_, args| {
                let Some(args) = args else { return Ok(()) };
                let mut suggested = PWSTR::null();
                args.ResultFilePath(&mut suggested)?;
                let suggested = PathBuf::from(take(suggested));
                let name = suggested.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
                let deferral = args.GetDeferral()?;
                let pending = MainThread((args, deferral));
                let Some(window) = app.get_webview_window(&label) else { return Ok(()) };
                let app = app.clone();
                let folder = app::download_dir();
                std::thread::spawn(move || {
                    let mut dialog = rfd::FileDialog::new().set_title("Сохранить файл").set_file_name(&name).set_parent(&window);
                    if let Some(folder) = folder {
                        dialog = dialog.set_directory(folder);
                    }
                    let path = dialog.save_file();
                    let _ = app.clone().run_on_main_thread(move || {
                        let (args, deferral) = pending.take();
                        unsafe {
                            match path {
                                Some(path) => {
                                    app::set_download_dir(&path);
                                    let _ = args.SetResultFilePath(&HSTRING::from(path.as_os_str()));
                                    let _ = args.SetHandled(true); // без всплывающей панели загрузок Edge
                                    if let Ok(op) = args.DownloadOperation() {
                                        watch_download(app, op, path);
                                    }
                                }
                                None => {
                                    let _ = args.SetCancel(true);
                                }
                            }
                            let _ = deferral.Complete();
                        }
                    });
                });
                Ok(())
            })),
            &mut token,
        )?;
    }

    // ---------- полноэкранное видео из страницы ----------
    {
        let (app, label) = (app.clone(), label.clone());
        webview.add_ContainsFullScreenElementChanged(
            &ContainsFullScreenElementChangedEventHandler::create(Box::new(move |sender, _| {
                let Some(sender) = sender else { return Ok(()) };
                let mut full = BOOL::default();
                sender.ContainsFullScreenElement(&mut full)?;
                if let Some(w) = app.get_webview_window(&label) {
                    let _ = w.set_fullscreen(full.as_bool());
                }
                Ok(())
            })),
            &mut token,
        )?;
    }

    // ---------- падение процесса страницы — перезагрузка через секунду ----------
    {
        let (app, label) = (app.clone(), label.clone());
        webview.add_ProcessFailed(
            &ProcessFailedEventHandler::create(Box::new(move |_, args| {
                let Some(args) = args else { return Ok(()) };
                let mut failed = COREWEBVIEW2_PROCESS_FAILED_KIND::default();
                args.ProcessFailedKind(&mut failed)?;
                log_process_failed(failed);
                if failed == COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_EXITED
                    || failed == COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_UNRESPONSIVE
                {
                    let (app, label) = (app.clone(), label.clone());
                    std::thread::spawn(move || {
                        std::thread::sleep(Duration::from_secs(1));
                        app::reload(&app, &label);
                    });
                } else if failed == COREWEBVIEW2_PROCESS_FAILED_KIND_BROWSER_PROCESS_EXITED {
                    app::on_browser_crash(&app, &label);
                }
                Ok(())
            })),
            &mut token,
        )?;
    }

    if kind == Kind::Main {
        // ---------- масштаб: Ctrl+колесо работает в самом WebView2 — приводим к своим шагам и запоминаем ----------
        let app_ = app.clone();
        controller.add_ZoomFactorChanged(
            &ZoomFactorChangedEventHandler::create(Box::new(move |sender, _| {
                let Some(sender) = sender else { return Ok(()) };
                let mut factor = 1.0;
                sender.ZoomFactor(&mut factor)?;
                let snapped = app::snap_zoom(factor);
                if (snapped - factor).abs() > 0.001 {
                    sender.SetZoomFactor(snapped)?;
                } else {
                    app::zoom_changed(&app_, factor);
                }
                Ok(())
            })),
            &mut token,
        )?;

        // ---------- окончание загрузки страницы: ошибки сети в режиме сервера, состояние окна ----------
        let (app_, controller_) = (app.clone(), controller.clone());
        webview.add_NavigationCompleted(
            &NavigationCompletedEventHandler::create(Box::new(move |sender, args| {
                let (Some(sender), Some(args)) = (sender, args) else { return Ok(()) };
                let mut ok = BOOL::default();
                args.IsSuccess(&mut ok)?;
                let mut status = COREWEBVIEW2_WEB_ERROR_STATUS::default();
                args.WebErrorStatus(&mut status)?;
                let mut http = 0i32;
                if let Ok(args2) = args.cast::<ICoreWebView2NavigationCompletedEventArgs2>() {
                    let _ = args2.HttpStatusCode(&mut http);
                }
                let mut source = PWSTR::null();
                sender.Source(&mut source)?;
                let source = take(source);
                let cancelled = status == COREWEBVIEW2_WEB_ERROR_STATUS_OPERATION_CANCELED;
                // масштаб WebView2 хранит для окна, но на всякий случай — после каждой загрузки
                let want = app::current_zoom();
                let mut factor = 1.0;
                let _ = controller_.ZoomFactor(&mut factor);
                if (factor - want).abs() > 0.001 {
                    let _ = controller_.SetZoomFactor(want);
                }
                let (app, ok, status) = (app_.clone(), ok.as_bool() || cancelled, status.0);
                let _ = app_.run_on_main_thread(move || app::on_navigation_completed(&app, &source, ok, status, http));
                Ok(())
            })),
            &mut token,
        )?;
    }

    attach_messages(&app, &label, &webview)
}

/// Сообщения страницы: window.chrome.webview.postMessage("tg-desktop:" + JSON) — из page.js, экранов оболочки
/// и окна подключения. Только строки: обработчик IPC wry на объекте возвращает ошибку, и WebView2 не зовёт
/// следующие обработчики (наш). Строку без формата Tauri его IPC пропускает, написав ошибку в консоль страницы.
unsafe fn attach_messages(app: &AppHandle, label: &str, webview: &ICoreWebView2) -> windows::core::Result<()> {
    let (app, label) = (app.clone(), label.to_string());
    let mut token = 0i64;
    webview.add_WebMessageReceived(
        &WebMessageReceivedEventHandler::create(Box::new(move |_, args| {
            let Some(args) = args else { return Ok(()) };
            let mut source = PWSTR::null();
            args.Source(&mut source)?;
            let source = take(source);
            let mut json = PWSTR::null();
            args.WebMessageAsJson(&mut json)?;
            let json = take(json);
            let text = serde_json::from_str::<String>(&json).unwrap_or_default();
            if let Some(msg) = text.strip_prefix(MESSAGE_PREFIX).and_then(|m| serde_json::from_str::<serde_json::Value>(m).ok()) {
                // после выхода из обработчика: создавать и закрывать окна WebView2 внутри его события нельзя
                let (app_, label) = (app.clone(), label.clone());
                let _ = app.run_on_main_thread(move || app::on_page_message(&app_, &label, &source, &msg));
            }
            Ok(())
        })),
        &mut token,
    )
}

fn key_action(kind: Kind, vk: u32, ctrl: bool, shift: bool, alt: bool) -> Option<app::Key> {
    use app::Key;
    const VK_R: u32 = 0x52;
    const VK_I: u32 = 0x49;
    const VK_Q: u32 = 0x51;
    const VK_W: u32 = 0x57;
    const VK_0: u32 = 0x30;
    const VK_F5: u32 = 0x74;
    const VK_F11: u32 = 0x7A;
    const VK_ESCAPE: u32 = 0x1B;
    const VK_OEM_PLUS: u32 = 0xBB;
    const VK_OEM_MINUS: u32 = 0xBD;
    const VK_ADD: u32 = 0x6B;
    const VK_SUBTRACT: u32 = 0x6D;
    const VK_NUMPAD0: u32 = 0x60;
    if alt || kind == Kind::Connect {
        return None;
    }
    match (vk, ctrl, shift) {
        (VK_F5, false, _) | (VK_R, true, false) => Some(Key::Reload),
        (VK_F11, false, false) => Some(Key::Fullscreen),
        (VK_I, true, true) => Some(Key::DevTools),
        (VK_Q, true, false) => Some(Key::Quit),
        (VK_OEM_PLUS | VK_ADD, true, _) if kind == Kind::Main => Some(Key::ZoomIn),
        (VK_OEM_MINUS | VK_SUBTRACT, true, _) if kind == Kind::Main => Some(Key::ZoomOut),
        (VK_0 | VK_NUMPAD0, true, false) if kind == Kind::Main => Some(Key::ZoomReset),
        (VK_ESCAPE, false, false) if kind == Kind::Media => Some(Key::Close),
        (VK_W, true, false) if matches!(kind, Kind::Media | Kind::Bot) => Some(Key::Close),
        _ => None,
    }
}

/// Окончание загрузки: «Файл сохранён» или сообщение об ошибке.
unsafe fn watch_download(app: AppHandle, op: ICoreWebView2DownloadOperation, path: PathBuf) {
    app::download_started();
    let mut token = 0i64;
    let mut done = false;
    let _ = op.add_StateChanged(
        &StateChangedEventHandler::create(Box::new(move |sender, _| {
            let Some(sender) = sender else { return Ok(()) };
            let mut state = COREWEBVIEW2_DOWNLOAD_STATE::default();
            sender.State(&mut state)?;
            if done || state == COREWEBVIEW2_DOWNLOAD_STATE_IN_PROGRESS {
                return Ok(());
            }
            done = true;
            if state == COREWEBVIEW2_DOWNLOAD_STATE_COMPLETED {
                app::download_finished(&app, &path, None);
            } else {
                let mut reason = COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON::default();
                sender.InterruptReason(&mut reason)?;
                let cancelled = reason == COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_USER_CANCELED;
                app::download_finished(&app, &path, if cancelled { Some(String::new()) } else { Some(interrupt_text(reason)) });
            }
            Ok(())
        })),
        &mut token,
    );
}

fn interrupt_text(reason: COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON) -> String {
    match reason {
        COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_FILE_ACCESS_DENIED => "нет доступа к папке".into(),
        COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_FILE_NO_SPACE => "на диске нет места".into(),
        COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_FILE_NAME_TOO_LONG => "слишком длинное имя файла".into(),
        COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_FILE_TOO_LARGE => "файл слишком большой для этого диска".into(),
        COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_FILE_BLOCKED_BY_POLICY
        | COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_FILE_MALICIOUS
        | COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_FILE_SECURITY_CHECK_FAILED => {
            "файл заблокирован проверкой безопасности".into()
        }
        COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_NETWORK_FAILED
        | COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_NETWORK_TIMEOUT
        | COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_NETWORK_DISCONNECTED
        | COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_NETWORK_SERVER_DOWN => "обрыв сети".into(),
        COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_SERVER_FAILED
        | COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_SERVER_BAD_CONTENT
        | COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_SERVER_NO_RANGE => "сервер не отдал файл".into(),
        COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_SERVER_UNAUTHORIZED | COREWEBVIEW2_DOWNLOAD_INTERRUPT_REASON_SERVER_FORBIDDEN => {
            "нет доступа к файлу на сервере".into()
        }
        other => format!("ошибка загрузки (код {})", other.0),
    }
}

/// Свой экран (status.html, connect.html) — из exe, без сервера и файлов на диске.
pub fn show_html(window: &WebviewWindow, html: String) {
    let _ = window.with_webview(move |pw| unsafe {
        if let Ok(webview) = pw.controller().CoreWebView2() {
            let _ = webview.NavigateToString(&HSTRING::from(html));
        }
    });
}

/// Ответ странице (окну подключения): postMessage в обратную сторону.
pub fn post(window: &WebviewWindow, msg: &serde_json::Value) {
    let json = msg.to_string();
    let _ = window.with_webview(move |pw| unsafe {
        if let Ok(webview) = pw.controller().CoreWebView2() {
            let _ = webview.PostWebMessageAsJson(&HSTRING::from(json));
        }
    });
}

pub fn reload(window: &WebviewWindow) {
    let _ = window.with_webview(|pw| unsafe {
        if let Ok(webview) = pw.controller().CoreWebView2() {
            let _ = webview.Reload();
        }
    });
}

/// Cookie входа (HttpOnly, path=/, 30 дней) — в профиль WebView2 до загрузки панели: из JS такую не поставить,
/// а пароль панели знает только программа. Потом — переход на адрес панели.
pub fn login_and_open(window: &WebviewWindow, url: tauri::Url, name: String, value: String) {
    let host = url.host_str().unwrap_or("127.0.0.1").to_string();
    let w = window.clone();
    let _ = window.with_webview(move |pw| {
        let result: windows::core::Result<()> = unsafe {
            (|| {
                let webview: ICoreWebView2_2 = pw.controller().CoreWebView2()?.cast()?;
                let cookies = webview.CookieManager()?;
                let cookie = cookies.CreateCookie(&HSTRING::from(name), &HSTRING::from(value), &HSTRING::from(host), &HSTRING::from("/"))?;
                cookie.SetIsHttpOnly(true)?;
                let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs_f64();
                cookie.SetExpires(now + 30.0 * 24.0 * 3600.0)?;
                cookies.AddOrUpdateCookie(&cookie)
            })()
        };
        if let Err(e) = result {
            log::error!("Не удалось передать cookie входа в WebView2: {e}");
        }
        // даём хранилищу cookie применить запись до первого запроса страницы (как QTimer 50 мс в shell.py)
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(50));
            let _ = w.navigate(url);
        });
    });
}

/// Есть ли WebView2 Runtime: без него окно не создать.
pub fn runtime_version() -> Option<String> {
    let mut version = PWSTR::null();
    unsafe { GetAvailableCoreWebView2BrowserVersionString(windows::core::PCWSTR::null(), &mut version).ok()? };
    let v = take(version);
    (!v.is_empty()).then_some(v)
}

fn log_process_failed(kind: COREWEBVIEW2_PROCESS_FAILED_KIND) {
    let what = match kind {
        COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_EXITED => "процесс страницы завершился — перезагружаем",
        COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_UNRESPONSIVE => "страница не отвечает — перезагружаем",
        COREWEBVIEW2_PROCESS_FAILED_KIND_BROWSER_PROCESS_EXITED => "процесс WebView2 завершился",
        _ => "вспомогательный процесс WebView2 завершился",
    };
    log::warn!("WebView2: {what} (вид {})", kind.0);
}
