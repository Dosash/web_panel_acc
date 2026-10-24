//! Журнал `<данные>\logs\tg-panel.log` с ротацией, как у прежней программы (2 МБ × 4 файла). Туда же —
//! журнал серверной части (её stderr, строки уже в формате Python logging) и ошибки JS страницы.

use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

const MAX_BYTES: u64 = 2_000_000;
const BACKUPS: u32 = 3;

struct FileLog {
    path: PathBuf,
    file: Mutex<Option<(File, u64)>>,
}

static LOG: OnceLock<FileLog> = OnceLock::new();

pub fn init(data: &Path) -> PathBuf {
    let dir = data.join("logs");
    let _ = fs::create_dir_all(&dir);
    let path = dir.join("tg-panel.log");
    let _ = LOG.set(FileLog { path: path.clone(), file: Mutex::new(None) });
    let _ = log::set_logger(&Logger);
    log::set_max_level(log::LevelFilter::Info);
    path
}

/// «2026-10-24 21:09:20,458» — как asctime у Python logging.
pub fn timestamp() -> String {
    let t = unsafe { windows::Win32::System::SystemInformation::GetLocalTime() };
    format!(
        "{:04}-{:02}-{:02} {:02}:{:02}:{:02},{:03}",
        t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond, t.wMilliseconds
    )
}

/// Готовая строка журнала (например, из stderr серверной части).
pub fn write_raw(line: &str) {
    let Some(log) = LOG.get() else { return };
    if cfg!(debug_assertions) {
        eprintln!("{line}");
    }
    let mut guard = log.file.lock().unwrap_or_else(|e| e.into_inner());
    let bytes = line.len() as u64 + 2;
    if let Some((_, size)) = guard.as_ref() {
        if size + bytes > MAX_BYTES {
            *guard = None; // закрыть перед переименованием
            rotate(&log.path);
        }
    }
    if guard.is_none() {
        if let Ok(f) = OpenOptions::new().create(true).append(true).open(&log.path) {
            let size = f.metadata().map(|m| m.len()).unwrap_or(0);
            *guard = Some((f, size));
        }
    }
    if let Some((f, size)) = guard.as_mut() {
        if f.write_all(format!("{line}\r\n").as_bytes()).is_ok() {
            *size += bytes;
        }
    }
}

fn rotate(path: &Path) {
    let name = |i: u32| PathBuf::from(format!("{}.{i}", path.display()));
    let _ = fs::remove_file(name(BACKUPS));
    for i in (1..BACKUPS).rev() {
        let _ = fs::rename(name(i), name(i + 1));
    }
    // файл может держать открытым помощник обновления — тогда просто пишем дальше в тот же
    let _ = fs::rename(path, name(1));
}

/// Запись в журнал из другого процесса той же папки данных (помощник обновления): открыть, дописать, закрыть.
pub fn append(data: &Path, logger: &str, level: &str, msg: &str) {
    let path = data.join("logs").join("tg-panel.log");
    let _ = fs::create_dir_all(path.parent().unwrap_or(data));
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        let _ = f.write_all(format!("{} {level} {logger}: {msg}\r\n", timestamp()).as_bytes());
    }
}

struct Logger;

impl log::Log for Logger {
    fn enabled(&self, meta: &log::Metadata) -> bool {
        // свои сообщения — от INFO, библиотек (tauri, wry) — только предупреждения и ошибки
        meta.level() <= log::Level::Warn || meta.target().starts_with("tg_panel")
    }

    fn log(&self, record: &log::Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        let level = match record.level() {
            log::Level::Error => "ERROR",
            log::Level::Warn => "WARNING",
            log::Level::Info => "INFO",
            _ => "DEBUG",
        };
        let target = record.target();
        let name = match target.strip_prefix("tg_panel") {
            Some("::updater") | Some("::helper") => "desktop.update",
            Some("::server") => "desktop.server",
            Some(_) => "desktop",
            None => target,
        };
        write_raw(&format!("{} {level} {name}: {}", timestamp(), record.args()));
    }

    fn flush(&self) {}
}
