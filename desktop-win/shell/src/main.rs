//! TG Panel для Windows: окно WebView2 (Tauri 2) к панели — своей (серверная часть рядом, локальный режим)
//! или на вашем сервере. См. desktop-win/README.md.
//!
//!   TG Panel.exe [--hidden]                 обычный запуск (--hidden — сразу в трей, так стартует автозапуск)
//!   TG Panel.exe --apply-update plan.json   помощник обновления (копия exe в папке данных, см. helper.rs)
//!   TG Panel.exe --check                    проверка, что программа запускается (помощник после установки)
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app;
mod autostart;
mod connection;
mod helper;
mod logger;
mod notify;
mod paths;
mod placement;
mod server;
mod settings;
mod tray;
mod updater;
mod webview;
mod winreg;

use std::time::Duration;

fn arg_value(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1).cloned())
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if let Some(plan) = arg_value(&args, "--apply-update") {
        std::process::exit(helper::run(&plan));
    }
    if args.iter().any(|a| a == "--check") {
        std::process::exit(if webview::runtime_version().is_some() { 0 } else { 3 });
    }
    // перезапуск (смена подключения): прежняя копия ещё отключает аккаунты — ждём её выхода
    if let Some(pid) = arg_value(&args, "--wait-pid").and_then(|p| p.parse().ok()) {
        helper::wait_pid(pid, Duration::from_secs(60));
    }
    let updated_from = arg_value(&args, "--updated-from").map(|from| {
        let started = arg_value(&args, "--update-started").and_then(|s| s.parse().ok()).unwrap_or_else(helper::now_ms);
        (from, started)
    });
    app::run(app::Args { hidden: args.iter().any(|a| a == "--hidden"), updated_from });
}
