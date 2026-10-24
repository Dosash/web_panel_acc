//! Настройки программы — `<данные>\desktop.ini` в формате QSettings (IniFormat), как у прежней программы
//! на PyQt5: после обновления режим, адрес сервера, порт, масштаб и прочее не спрашиваются заново.
//! Незнакомые ключи (geometry окна Qt и т.п.) сохраняются как были.

use std::fs;
use std::path::{Path, PathBuf};

pub struct Settings {
    path: PathBuf,
    /// [General]: ключ → значение в записи QSettings (с экранированием)
    general: Vec<(String, String)>,
    /// всё остальное (другие разделы) — без изменений
    rest: Vec<String>,
}

impl Settings {
    pub fn load(path: &Path) -> Self {
        let mut s = Settings { path: path.to_path_buf(), general: Vec::new(), rest: Vec::new() };
        let Ok(text) = fs::read_to_string(path) else { return s };
        let mut section = String::new();
        for line in text.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with('[') && trimmed.ends_with(']') {
                section = trimmed[1..trimmed.len() - 1].to_string();
                if section != "General" {
                    s.rest.push(line.to_string());
                }
                continue;
            }
            if section == "General" || section.is_empty() {
                if let Some((k, v)) = trimmed.split_once('=') {
                    s.general.push((k.trim().to_string(), v.trim().to_string()));
                }
            } else {
                s.rest.push(line.to_string());
            }
        }
        s
    }

    fn raw(&self, key: &str) -> Option<&str> {
        self.general.iter().find(|(k, _)| k == key).map(|(_, v)| v.as_str())
    }

    pub fn get(&self, key: &str) -> Option<String> {
        self.raw(key).map(unescape).filter(|v| !v.is_empty())
    }

    pub fn get_bool(&self, key: &str, default: bool) -> bool {
        match self.get(key).as_deref() {
            Some("true") | Some("1") => true,
            Some("false") | Some("0") => false,
            _ => default,
        }
    }

    pub fn get_f64(&self, key: &str) -> Option<f64> {
        let raw = self.raw(key)?;
        if raw.starts_with("@Variant(") {
            return variant_double(raw);
        }
        unescape(raw).parse().ok()
    }

    pub fn get_u16(&self, key: &str) -> Option<u16> {
        self.get(key)?.parse().ok()
    }

    pub fn set(&mut self, key: &str, value: impl ToString) {
        let value = escape(&value.to_string());
        match self.general.iter_mut().find(|(k, _)| k == key) {
            Some(entry) => entry.1 = value,
            None => self.general.push((key.to_string(), value)),
        }
    }

    /// Запись через временный файл — обрыв питания не оставит пустой desktop.ini.
    pub fn save(&self) {
        let mut out = String::from("[General]\r\n");
        for (k, v) in &self.general {
            out.push_str(&format!("{k}={v}\r\n"));
        }
        for line in &self.rest {
            out.push_str(line);
            out.push_str("\r\n");
        }
        if let Some(dir) = self.path.parent() {
            let _ = fs::create_dir_all(dir);
        }
        let tmp = self.path.with_extension("ini.tmp");
        if fs::write(&tmp, out).is_ok() && fs::rename(&tmp, &self.path).is_err() {
            log::warn!("Не удалось сохранить настройки в {}", self.path.display());
        }
    }
}

/// Строка в записи QSettings: \\, \", \xHEX для не-ASCII; в кавычках, если есть , ; = или пробелы по краям.
fn escape(value: &str) -> String {
    let mut out = String::new();
    let mut escape_next_hex = false;
    for ch in value.chars() {
        if escape_next_hex && ch.is_ascii_hexdigit() {
            out.push_str(&format!("\\x{:x}", ch as u32));
            continue;
        }
        escape_next_hex = false;
        match ch {
            '\\' => out.push_str("\\\\"),
            '"' => out.push_str("\\\""),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 || (c as u32) >= 0x7f => {
                out.push_str(&format!("\\x{:x}", c as u32));
                escape_next_hex = true;
            }
            c => out.push(c),
        }
    }
    let quote = value.contains([',', ';', '=']) || value.starts_with(' ') || value.ends_with(' ');
    if quote {
        format!("\"{out}\"")
    } else {
        out
    }
}

/// Обратное к QSettings: кавычки, \-последовательности, \xHEX (Qt пишет так не-ASCII символы).
fn unescape(raw: &str) -> String {
    let mut out = String::new();
    let mut chars = raw.chars().peekable();
    while let Some(ch) = chars.next() {
        match ch {
            '"' => {}
            '\\' => match chars.next() {
                Some('x') => {
                    let mut hex = String::new();
                    while let Some(c) = chars.peek().filter(|c| c.is_ascii_hexdigit()) {
                        hex.push(*c);
                        chars.next();
                    }
                    if let Some(c) = u32::from_str_radix(&hex, 16).ok().and_then(char::from_u32) {
                        out.push(c);
                    }
                }
                Some('n') => out.push('\n'),
                Some('r') => out.push('\r'),
                Some('t') => out.push('\t'),
                Some('0') => out.push('\0'),
                Some(c) => out.push(c),
                None => {}
            },
            c => out.push(c),
        }
    }
    out
}

/// `@Variant(\0\0\0\x6\0…)` — так Qt 5 пишет double: тип 6, флаг null, 8 байт big-endian.
fn variant_double(raw: &str) -> Option<f64> {
    let body = raw.strip_prefix("@Variant(")?.strip_suffix(')')?;
    let mut bytes = Vec::new();
    let mut chars = body.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch != '\\' {
            bytes.push(ch as u8);
            continue;
        }
        match chars.next()? {
            '0' => bytes.push(0),
            'x' => {
                let mut hex = String::new();
                while hex.len() < 2 {
                    match chars.peek() {
                        Some(c) if c.is_ascii_hexdigit() => {
                            hex.push(*c);
                            chars.next();
                        }
                        _ => break,
                    }
                }
                bytes.push(u8::from_str_radix(&hex, 16).ok()?);
            }
            c => bytes.push(c as u8),
        }
    }
    if bytes.len() < 13 || u32::from_be_bytes(bytes[0..4].try_into().ok()?) != 6 {
        return None;
    }
    Some(f64::from_be_bytes(bytes[5..13].try_into().ok()?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        for v in ["http://192.168.3.18/accounts/", "C:/Users/Дима/Загрузки", "a,b", " x", "C:\\temp"] {
            assert_eq!(unescape(&escape(v)), v);
        }
        assert_eq!(unescape("C:/Users/\\x414\\x438\\x43c\\x430/Downloads"), "C:/Users/Дима/Downloads");
    }

    #[test]
    fn qt_double() {
        assert_eq!(variant_double("@Variant(\\0\\0\\0\\x6\\0?\\xf4\\0\\0\\0\\0\\0\\0)"), Some(1.25));
    }
}
