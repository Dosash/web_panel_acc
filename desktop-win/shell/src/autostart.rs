//! Запуск при входе в систему: значение «TG Panel» в HKCU\…\Run (то же имя удаляет деинсталлятор),
//! программа стартует свёрнутой в трей (--hidden).

use crate::paths;
use crate::winreg::{self, HKCU};

const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";

fn command() -> String {
    format!("\"{}\" --hidden", paths::exe().display())
}

pub fn enabled() -> bool {
    winreg::get_string(HKCU, RUN_KEY, paths::APP_NAME).is_some()
}

pub fn set_enabled(on: bool) -> windows::core::Result<()> {
    if on {
        winreg::set_string(HKCU, RUN_KEY, paths::APP_NAME, &command())
    } else {
        winreg::delete_value(HKCU, RUN_KEY, paths::APP_NAME);
        Ok(())
    }
}

/// Автозапуск указывает на программу, которой уже нет (перенесли папку, сменили установку
/// «для всех» на «для себя»), — переводим его на эту копию.
pub fn repair() {
    let Some(current) = winreg::get_string(HKCU, RUN_KEY, paths::APP_NAME) else { return };
    let target = current.trim().trim_start_matches('"');
    let exe = target.split('"').next().unwrap_or(target);
    let exe = exe.strip_suffix(" --hidden").unwrap_or(exe);
    if !std::path::Path::new(exe).exists() {
        log::info!("Автозапуск указывал на {exe} — теперь на {}", paths::exe().display());
        let _ = set_enabled(true);
    }
}
