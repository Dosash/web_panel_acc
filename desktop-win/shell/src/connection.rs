//! Где работают аккаунты: на этом компьютере (свой сервер панели рядом с программой) или на вашем сервере —
//! тогда программа просто открывает веб-панель. Повторяет desktop/connection.py.

use std::time::Duration;

pub const LOCAL: &str = "local";
pub const REMOTE: &str = "remote";

/// '192.168.1.10/accounts' → 'http://192.168.1.10/accounts/': адреса панели относительные,
/// без слэша в конце api/... ушли бы мимо её пути.
pub fn normalize_url(text: &str) -> String {
    let mut url = text.trim().to_string();
    if !url.is_empty() && !url.contains("://") {
        url = format!("http://{url}");
    }
    if !url.ends_with('/') {
        url.push('/');
    }
    url
}

pub fn http_client(timeout: Duration) -> reqwest::Result<reqwest::blocking::Client> {
    reqwest::blocking::Client::builder()
        .user_agent("TG-Panel-Desktop")
        .timeout(timeout)
        .build()
}

/// None — по адресу отвечает TG Panel, иначе текст ошибки. /api/health открыт без пароля.
/// Блокирующий вызов — только из фонового потока.
pub fn check_server(url: &str) -> Option<String> {
    let client = match http_client(Duration::from_secs(6)) {
        Ok(c) => c,
        Err(e) => return Some(e.to_string()),
    };
    let resp = match client.get(format!("{url}api/health")).send() {
        Ok(r) => r,
        Err(e) => return Some(format!("нет связи: {}", short_error(&e))),
    };
    if !resp.status().is_success() {
        return Some(format!(
            "сервер ответил {} — проверьте путь панели (например, /accounts/)",
            resp.status().as_u16()
        ));
    }
    match resp.json::<serde_json::Value>() {
        Ok(data) if data.get("version").is_some() => None,
        _ => Some("по этому адресу не TG Panel".into()),
    }
}

/// Причина ошибки сети без цепочки «error sending request for url (…)».
pub fn short_error(e: &reqwest::Error) -> String {
    use std::error::Error;
    let mut cause: &dyn Error = e;
    while let Some(next) = cause.source() {
        cause = next;
    }
    if e.is_timeout() {
        "сервер не ответил вовремя".into()
    } else if e.is_connect() {
        format!("не удалось подключиться ({cause})")
    } else {
        cause.to_string()
    }
}
