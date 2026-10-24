//! Где программа держит данные и где лежат её файлы — те же места, что у прежней программы (desktop/paths.py).

use std::path::{Path, PathBuf};

pub const APP_NAME: &str = "TG Panel";
/// AppUserModelID: значок на панели задач и имя в уведомлениях (как у прежней программы)
pub const AUMID: &str = "TGPanel.Desktop";
pub const VERSION: &str = env!("TG_PANEL_VERSION");

pub fn exe() -> PathBuf {
    std::env::current_exe().unwrap_or_else(|_| PathBuf::from("TG Panel.exe"))
}

/// Папка программы: `TG Panel.exe`, `server\`, у переносной — `portable.txt` и `data\`.
pub fn app_dir() -> PathBuf {
    exe().parent().map(Path::to_path_buf).unwrap_or_default()
}

/// Переносная версия (zip): рядом с программой лежит portable.txt, данные — в папке data рядом.
pub fn portable() -> bool {
    app_dir().join("portable.txt").exists()
}

/// База, ключ шифрования сессий, кэш, профиль WebView2, журнал. Не в папке программы:
/// обновление или переустановка не трогают аккаунты. TG_PANEL_DATA — другая папка.
pub fn data_dir() -> PathBuf {
    if let Ok(custom) = std::env::var("TG_PANEL_DATA") {
        let custom = custom.trim();
        if !custom.is_empty() {
            let p = PathBuf::from(custom);
            return std::path::absolute(&p).unwrap_or(p);
        }
    }
    if portable() {
        return app_dir().join("data");
    }
    let appdata = std::env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(std::env::var_os("USERPROFILE").unwrap_or_default()).join("AppData\\Roaming"));
    appdata.join(APP_NAME)
}

/// Команда запуска серверной части. В сборке — `server\tg-panel-server.exe` рядом с программой;
/// при разработке (cargo run) — main.py из репозитория через Python из desktop-win\.venv.
pub fn server_command() -> Vec<PathBuf> {
    let exe = app_dir().join("server").join("tg-panel-server.exe");
    if exe.exists() || !cfg!(debug_assertions) {
        return vec![exe];
    }
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
    vec![repo.join(".venv\\Scripts\\python.exe"), repo.join("server\\main.py")]
}

/// Короткий отпечаток папки данных — для имён «одна копия на папку данных».
pub fn data_tag(data: &Path) -> String {
    // FNV-1a: стабилен между версиями (в отличие от DefaultHasher)
    let mut h: u64 = 0xcbf29ce484222325;
    for b in data.to_string_lossy().to_lowercase().bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    format!("{:012x}", h & 0xffff_ffff_ffff)
}

pub fn parse_version(v: &str) -> (u32, u32, u32) {
    let mut nums = v
        .split(|c: char| !c.is_ascii_digit())
        .filter(|s| !s.is_empty())
        .map(|s| s.parse::<u32>().unwrap_or(0));
    (nums.next().unwrap_or(0), nums.next().unwrap_or(0), nums.next().unwrap_or(0))
}

pub fn newer(a: &str, b: &str) -> bool {
    parse_version(a) > parse_version(b)
}
