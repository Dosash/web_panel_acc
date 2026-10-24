//! Значок в трее: щелчок — показать/скрыть окно, меню — как у прежней программы (desktop/shell.py build_menu).

use tauri::menu::{CheckMenuItem, Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Wry};

use crate::{app, autostart, paths, updater};

pub struct Tray {
    pub icon: TrayIcon,
    pub connection: MenuItem<Wry>,
    pub update: MenuItem<Wry>,
    pub auto_update: CheckMenuItem<Wry>,
    pub autostart: CheckMenuItem<Wry>,
}

pub fn build(app: &AppHandle) -> tauri::Result<Tray> {
    let open = MenuItem::with_id(app, "open", "Открыть TG Panel", true, None::<&str>)?;
    let connection = MenuItem::with_id(app, "connection", connection_text(), true, None::<&str>)?;
    let data = MenuItem::with_id(app, "data", "Папка с данными", true, None::<&str>)?;
    let update = MenuItem::with_id(app, "update", "Проверить обновления", true, None::<&str>)?;
    let auto_update = CheckMenuItem::with_id(app, "auto_update", "Обновлять автоматически", true, app::auto_update(), None::<&str>)?;
    let autostart = CheckMenuItem::with_id(app, "autostart", "Запускать при входе в систему", true, autostart::enabled(), None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Выход", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &open,
            &connection,
            &data,
            &PredefinedMenuItem::separator(app)?,
            &update,
            &auto_update,
            &autostart,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;
    let mut builder = TrayIconBuilder::with_id("main")
        .tooltip(format!("{} {}", paths::APP_NAME, paths::VERSION))
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(on_menu)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                app::toggle_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    let icon = builder.build(app)?;
    Ok(Tray { icon, connection, update, auto_update, autostart })
}

pub fn connection_text() -> String {
    match app::mode().as_str() {
        crate::connection::LOCAL => "Подключение: на этом компьютере…".into(),
        crate::connection::REMOTE => format!("Подключение: {}…", app::server_url().unwrap_or_else(|| "сервер".into())),
        _ => "Подключение…".into(),
    }
}

fn on_menu(app: &AppHandle, event: MenuEvent) {
    match event.id().as_ref() {
        "open" => app::show_main(app),
        "connection" => app::open_connect(app, false),
        "data" => app::shell_open(&app::shell().data.to_string_lossy()),
        "update" => updater::tray_clicked(app),
        "auto_update" => app::with_tray(|t| app::set_auto_update(t.auto_update.is_checked().unwrap_or(true))),
        "autostart" => app::with_tray(|t| {
            let on = t.autostart.is_checked().unwrap_or(false);
            if let Err(e) = autostart::set_enabled(on) {
                let _ = t.autostart.set_checked(!on);
                app::message(app, &format!("Не удалось изменить автозапуск: {e}"));
            }
        }),
        "quit" => app::quit(app, app::After::Nothing),
        _ => {}
    }
}
