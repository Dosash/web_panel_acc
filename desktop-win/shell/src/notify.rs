//! Системные уведомления Windows от имени «TG Panel» (AppUserModelID TGPanel.Desktop): уведомления страницы
//! (new Notification), «Файл сохранён», обновления. Щелчок по уведомлению открывает окно программы.

use std::path::Path;
use std::sync::Mutex;

use tauri::AppHandle;
use windows::core::HSTRING;
use windows::Data::Xml::Dom::XmlDocument;
use windows::Foundation::TypedEventHandler;
use windows::UI::Notifications::{ToastNotification, ToastNotificationManager};

use crate::paths::{APP_NAME, AUMID};
use crate::winreg::{self, HKCU};

/// Показанные уведомления: объект должен жить, пока его могут щёлкнуть
static SHOWN: Mutex<Vec<ToastNotification>> = Mutex::new(Vec::new());

/// Имя и значок для уведомлений программы без ярлыка с AppUserModelID (переносная версия, первый запуск).
/// Установщик вдобавок ставит этот ID ярлыку в меню «Пуск».
pub fn register(data: &Path) {
    let icon = data.join("tg-panel.png");
    if !icon.exists() {
        let _ = std::fs::write(&icon, include_bytes!("../icons/128x128@2x.png"));
    }
    let key = format!(r"Software\Classes\AppUserModelId\{AUMID}");
    let _ = winreg::set_string(HKCU, &key, "DisplayName", APP_NAME);
    let _ = winreg::set_string(HKCU, &key, "IconUri", &icon.to_string_lossy());
    unsafe {
        let _ = windows::Win32::UI::Shell::SetCurrentProcessExplicitAppUserModelID(&HSTRING::from(AUMID));
    }
}

fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;")
}

pub fn show(app: &AppHandle, title: &str, body: &str) {
    if let Err(e) = try_show(app, title, body) {
        log::warn!("Уведомление не показано: {e}");
    }
}

fn try_show(app: &AppHandle, title: &str, body: &str) -> windows::core::Result<()> {
    let body: String = body.chars().take(300).collect();
    let xml = format!(
        "<toast><visual><binding template=\"ToastGeneric\"><text>{}</text><text>{}</text></binding></visual></toast>",
        xml_escape(title),
        xml_escape(&body)
    );
    let doc = XmlDocument::new()?;
    doc.LoadXml(&HSTRING::from(xml))?;
    let toast = ToastNotification::CreateToastNotification(&doc)?;
    let app = app.clone();
    toast.Activated(&TypedEventHandler::new(move |_, _| {
        let app = app.clone();
        let _ = app.clone().run_on_main_thread(move || crate::app::show_main(&app));
        Ok(())
    }))?;
    ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(AUMID))?.Show(&toast)?;
    let mut shown = SHOWN.lock().unwrap_or_else(|e| e.into_inner());
    shown.push(toast);
    if shown.len() > 30 {
        shown.remove(0);
    }
    Ok(())
}
