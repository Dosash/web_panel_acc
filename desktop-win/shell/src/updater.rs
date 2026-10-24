//! Фоновое обновление из GitHub Releases. Совместимо с прежней программой: те же имена файлов релиза
//! (`TG-Panel-<версия>-windows-x64-setup.exe` / `-portable.zip`), тот же адрес API (TG_PANEL_UPDATE_URL — свой).
//!
//! Проверка через 30 с после запуска и раз в 6 часов; скачивание — в фоне, с докачкой и повторами; файл
//! сверяется с `TG-Panel-<версия>-SHA256SUMS.txt` из того же релиза (нет суммы или не совпала — не ставим).
//! Ставит помощник (helper.rs) после выхода программы: когда окно в трее и программа простаивает, при выходе,
//! при следующем запуске или по кнопке «Перезапустить» на плашке в окне. Сломанная версия откатывается
//! и больше не ставится (state.json → bad).

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tauri::AppHandle;

use crate::app::{self, After};
use crate::connection::{http_client, short_error};
use crate::paths::{self, newer, VERSION};

pub const REPO: &str = "Dosash/web_panel_acc";
const FIRST_CHECK: Duration = Duration::from_secs(30);
const CHECK_EVERY: Duration = Duration::from_secs(6 * 3600);
/// после неудачной проверки или загрузки (нет сети) — следующая попытка раньше обычного
const RETRY_CHECK: Duration = Duration::from_secs(30 * 60);
/// паузы между попытками докачать файл при обрыве
const RETRY_DELAYS: [u64; 5] = [5, 15, 30, 60, 120];
/// окно в трее столько времени — можно ставить
const IDLE_BEFORE_INSTALL: Duration = Duration::from_secs(60);

fn api_url() -> String {
    std::env::var("TG_PANEL_UPDATE_URL")
        .ok()
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| format!("https://api.github.com/repos/{REPO}/releases/latest"))
}

#[derive(Clone, Debug)]
struct Asset {
    name: String,
    url: String,
    size: u64,
}

#[derive(Clone, Debug)]
pub struct Release {
    pub version: String,
    notes: String,
    page: String,
    asset: Option<Asset>,
    sums: Option<Asset>,
}

/// Скачанное и проверенное обновление — ждёт установки (и переживает перезапуск: state.json → pending).
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Ready {
    pub version: String,
    pub notes: String,
    pub kind: String,
    pub file: PathBuf,
    pub sha256: String,
    /// переносная версия: распакованная папка «TG Panel»
    pub stage: Option<PathBuf>,
}

#[derive(Default)]
struct Inner {
    busy: bool,
    manual: bool,
    found: Option<Release>,
    ready: Option<Ready>,
    /// установка «для всех» → переход на установку для пользователя (согласие получено)
    to_user: bool,
    next_check: Option<Instant>,
}

static INNER: Mutex<Option<Inner>> = Mutex::new(None);

fn with<T>(f: impl FnOnce(&mut Inner) -> T) -> T {
    let mut guard = INNER.lock().unwrap_or_else(|e| e.into_inner());
    f(guard.get_or_insert_with(Inner::default))
}

/// Как установлена программа: установщик (рядом unins000.exe), переносная (portable.txt) или запуск
/// из папки сборки — тогда только сообщаем о новой версии.
pub fn install_kind() -> Option<&'static str> {
    if paths::portable() {
        Some("portable")
    } else if paths::app_dir().join("unins000.exe").exists() {
        Some("setup")
    } else {
        None
    }
}

fn asset_suffix(kind: &str) -> &'static str {
    if kind == "portable" { "-windows-x64-portable.zip" } else { "-windows-x64-setup.exe" }
}

fn dir_writable(dir: &Path) -> bool {
    let probe = dir.join(format!(".tg-panel-write-{}", std::process::id()));
    let ok = File::create(&probe).is_ok();
    let _ = fs::remove_file(&probe);
    ok
}

/// Установка «для всех» (Program Files): обновление без прав администратора туда не запишет.
pub fn needs_admin() -> bool {
    install_kind() == Some("setup") && !dir_writable(&paths::app_dir())
}

// ---------- state.json: отложенная установка, сломанные версии, «обновлено до» ----------

pub fn state_path(data: &Path) -> PathBuf {
    data.join("update").join("state.json")
}

pub fn load_state(data: &Path) -> Value {
    fs::read_to_string(state_path(data))
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({}))
}

pub fn save_state(data: &Path, state: &Value) {
    let path = state_path(data);
    let _ = fs::create_dir_all(path.parent().unwrap_or(data));
    let tmp = path.with_extension("json.tmp");
    if fs::write(&tmp, serde_json::to_vec_pretty(state).unwrap_or_default()).is_ok() {
        let _ = fs::rename(&tmp, &path);
    }
}

pub fn update_state(data: &Path, f: impl FnOnce(&mut serde_json::Map<String, Value>)) {
    let mut state = load_state(data);
    if let Some(map) = state.as_object_mut() {
        f(map);
    }
    save_state(data, &state);
}

pub fn is_bad(data: &Path, version: &str) -> bool {
    load_state(data)["bad"].as_array().is_some_and(|a| a.iter().any(|v| v == version))
}

// ---------- проверка ----------

fn fetch_latest() -> Result<Release, String> {
    let client = http_client(Duration::from_secs(20)).map_err(|e| e.to_string())?;
    let resp = client
        .get(api_url())
        .header("Accept", "application/vnd.github+json")
        .send()
        .map_err(|e| short_error(&e))?;
    if !resp.status().is_success() {
        return Err(format!("GitHub ответил {}", resp.status().as_u16()));
    }
    let data: Value = resp.json().map_err(|e| format!("непонятный ответ GitHub: {e}"))?;
    let version = data["tag_name"].as_str().unwrap_or_default().trim_start_matches('v').to_string();
    let mut rel = Release {
        version,
        notes: data["body"].as_str().unwrap_or_default().trim().to_string(),
        page: data["html_url"].as_str().map(str::to_string).unwrap_or_else(|| format!("https://github.com/{REPO}/releases/latest")),
        asset: None,
        sums: None,
    };
    let suffix = asset_suffix(install_kind().unwrap_or("setup"));
    for a in data["assets"].as_array().into_iter().flatten() {
        let name = a["name"].as_str().unwrap_or_default();
        let asset = || Asset {
            name: name.to_string(),
            url: a["browser_download_url"].as_str().unwrap_or_default().to_string(),
            size: a["size"].as_u64().unwrap_or(0),
        };
        if name.ends_with(suffix) {
            rel.asset = Some(asset());
        } else if name.ends_with("SHA256SUMS.txt") {
            rel.sums = Some(asset());
        }
    }
    Ok(rel)
}

pub fn start(app: &AppHandle) {
    // заготовка «готово к установке» после перезапуска: скачанный ранее файл ещё раз сверяем
    if let Some(ready) = pending(&app::shell().data) {
        log::info!("Обновление {} уже скачано — поставим при удобном случае", ready.version);
        with(|s| s.ready = Some(ready));
        on_ready(app);
    }
    let timer = app.clone();
    std::thread::Builder::new()
        .name("update-timer".into())
        .spawn(move || {
            std::thread::sleep(FIRST_CHECK);
            loop {
                if app::quitting() {
                    return;
                }
                let due = with(|s| s.next_check.is_none_or(|t| Instant::now() >= t));
                if due {
                    with(|s| s.next_check = Some(Instant::now() + CHECK_EVERY));
                    check(&timer, false);
                }
                std::thread::sleep(Duration::from_secs(20));
                idle_install(&timer);
            }
        })
        .ok();
}

/// Проверить обновления. manual — из трея или из окна панели: тогда сообщаем и «последняя версия», и ошибки.
pub fn check(app: &AppHandle, manual: bool) {
    let has_ready = with(|s| s.ready.is_some());
    if has_ready {
        if manual {
            install_now(app);
        }
        return;
    }
    if !manual && !app::auto_update() && with(|s| s.found.is_some()) {
        return; // о новой версии уже сообщили, скачивать без согласия не нужно
    }
    let started = with(|s| {
        if s.busy {
            s.manual |= manual;
            return false;
        }
        s.busy = true;
        s.manual = manual;
        true
    });
    if !started {
        if manual {
            app::notify(app, paths::APP_NAME, "Проверяем обновления…");
        }
        return;
    }
    let app = app.clone();
    std::thread::Builder::new()
        .name("update-check".into())
        .spawn(move || {
            let result = run_check(&app);
            let manual = with(|s| {
                s.busy = false;
                s.manual
            });
            if let Err(e) = result {
                log::warn!("Обновление не удалось: {e}");
                with(|s| s.next_check = Some(Instant::now() + RETRY_CHECK));
                if manual {
                    app::message(&app, &format!("Не удалось проверить обновления:\n{e}"));
                }
            }
        })
        .ok();
}

fn run_check(app: &AppHandle) -> Result<(), String> {
    let data = app::shell().data.clone();
    let rel = fetch_latest()?;
    let manual = with(|s| s.manual);
    if rel.version.is_empty() || !newer(&rel.version, VERSION) {
        log::info!("Обновлений нет: последняя версия {}", if rel.version.is_empty() { VERSION } else { &rel.version });
        if manual {
            app::message(app, &format!("У вас последняя версия: {VERSION}."));
        }
        return Ok(());
    }
    if is_bad(&data, &rel.version) {
        log::warn!("Версия {} уже не запустилась на этом компьютере — не ставим её снова", rel.version);
        if manual {
            app::message(
                app,
                &format!("TG Panel {} не запустилась на этом компьютере, и программа вернулась к {VERSION}. Эту версию \
                          она больше не ставит — дождитесь следующей или скачайте вручную со страницы релиза.", rel.version),
            );
        }
        return Ok(());
    }
    log::info!("Доступна версия {} (сейчас {VERSION})", rel.version);
    with(|s| s.found = Some(rel.clone()));
    app::set_update_text(&format!("Обновить до {}", rel.version));

    let kind = install_kind();
    if kind.is_none() || rel.asset.is_none() {
        // запуск из папки сборки или в релизе нет файла под Windows — только ссылка
        let notified = app::setting("notified_version");
        if manual || notified.as_deref() != Some(rel.version.as_str()) {
            app::set_setting("notified_version", &rel.version);
            let text = format!("Доступна TG Panel {} (у вас {VERSION}).\nОткрыть страницу загрузки?", rel.version);
            if app::ask_main(app, &text) {
                app::shell_open(&rel.page);
            }
        }
        return Ok(());
    }
    if !manual && !app::auto_update() {
        // автообновление выключено — один раз сказать о версии
        if app::setting("notified_version").as_deref() != Some(rel.version.as_str()) {
            app::set_setting("notified_version", &rel.version);
            app::notify(
                app,
                &format!("Доступна TG Panel {}", rel.version),
                &format!("Обновить: значок в трее → «Обновить до {}»", rel.version),
            );
        }
        return Ok(());
    }
    if manual {
        app::notify(app, paths::APP_NAME, &format!("Скачиваем TG Panel {}…", rel.version));
    }
    let ready = download(&data, &rel, kind.unwrap_or("setup"))?;
    update_state(&data, |s| {
        s.insert("pending".into(), serde_json::to_value(&ready).unwrap_or_default());
    });
    with(|s| s.ready = Some(ready));
    on_ready(app);
    Ok(())
}

// ---------- загрузка ----------

fn sha256_file(path: &Path) -> std::io::Result<String> {
    let mut f = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    loop {
        let n = f.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hasher.finalize().iter().map(|b| format!("{b:02x}")).collect())
}

/// `<sha256>  <имя файла>` (формат sha256sum) → сумма для нужного файла.
fn expected_sum(sums: &Asset, name: &str) -> Result<String, String> {
    let client = http_client(Duration::from_secs(30)).map_err(|e| e.to_string())?;
    let resp = client.get(&sums.url).send().map_err(|e| short_error(&e))?;
    if !resp.status().is_success() {
        return Err(format!("файл контрольных сумм: сервер ответил {}", resp.status().as_u16()));
    }
    let text = resp.text().map_err(|e| short_error(&e))?;
    text.lines()
        .filter_map(|l| {
            let (hash, file) = l.trim().split_once(char::is_whitespace)?;
            (file.trim().trim_start_matches('*') == name).then(|| hash.to_ascii_lowercase())
        })
        .find(|h| h.len() == 64 && h.chars().all(|c| c.is_ascii_hexdigit()))
        .ok_or_else(|| format!("в файле контрольных сумм нет {name} — обновление не ставим"))
}

fn download(data: &Path, rel: &Release, kind: &str) -> Result<Ready, String> {
    let asset = rel.asset.clone().ok_or("в релизе нет файла для Windows")?;
    let sums = rel.sums.clone().ok_or("в релизе нет файла контрольных сумм — обновление не ставим")?;
    let expected = expected_sum(&sums, &asset.name)?;
    let dir = data.join("update").join(&rel.version);
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let file = dir.join(&asset.name);
    let part = dir.join(format!("{}.part", asset.name));
    let have_ok = file.exists() && sha256_file(&file).is_ok_and(|h| h == expected);
    if !have_ok {
        let _ = fs::remove_file(&file);
        let started = Instant::now();
        let mut attempt = 0;
        loop {
            match download_part(&asset, &part) {
                Ok(()) => break,
                Err(e) if attempt < RETRY_DELAYS.len() => {
                    let have = fs::metadata(&part).map(|m| m.len()).unwrap_or(0);
                    log::warn!("Загрузка {} прервалась ({e}), есть {have} из {} байт — повтор через {} с",
                        asset.name, asset.size, RETRY_DELAYS[attempt]);
                    std::thread::sleep(Duration::from_secs(RETRY_DELAYS[attempt]));
                    attempt += 1;
                }
                Err(e) => return Err(format!("не удалось скачать {}: {e}", asset.name)),
            }
            if app::quitting() {
                return Err("программа закрывается".into());
            }
        }
        let size = fs::metadata(&part).map(|m| m.len()).unwrap_or(0);
        let actual = sha256_file(&part).map_err(|e| e.to_string())?;
        if (asset.size > 0 && size != asset.size) || actual != expected {
            let _ = fs::remove_file(&part);
            log::error!("Файл {} не совпал с контрольной суммой (ожидалась {expected}, получена {actual}) — удалён", asset.name);
            return Err(format!("файл {} повреждён или подменён: контрольная сумма не совпала", asset.name));
        }
        fs::rename(&part, &file).map_err(|e| e.to_string())?;
        log::info!("Скачано и проверено: {} ({:.1} МБ за {:.0} с)", asset.name, size as f64 / 1e6, started.elapsed().as_secs_f32());
    }
    let stage = if kind == "portable" { Some(unpack(&file, &dir.join("unzip"))?) } else { None };
    Ok(Ready { version: rel.version.clone(), notes: rel.notes.clone(), kind: kind.into(), file, sha256: expected, stage })
}

/// Один заход загрузки: докачка с места обрыва (Range), если сервер умеет; иначе — заново.
fn download_part(asset: &Asset, part: &Path) -> Result<(), String> {
    let mut have = fs::metadata(part).map(|m| m.len()).unwrap_or(0);
    if asset.size > 0 && have == asset.size {
        return Ok(());
    }
    if asset.size > 0 && have > asset.size {
        let _ = fs::remove_file(part);
        have = 0;
    }
    let client = reqwest::blocking::Client::builder()
        .user_agent("TG-Panel-Desktop")
        .connect_timeout(Duration::from_secs(20))
        .timeout(Duration::from_secs(30 * 60))
        .build()
        .map_err(|e| e.to_string())?;
    let mut req = client.get(&asset.url);
    if have > 0 {
        req = req.header("Range", format!("bytes={have}-"));
    }
    let mut resp = req.send().map_err(|e| short_error(&e))?;
    let status = resp.status().as_u16();
    let mut out = match status {
        206 => OpenOptions::new().append(true).open(part).map_err(|e| e.to_string())?,
        200 => File::create(part).map_err(|e| e.to_string())?, // докачку сервер не умеет — с начала
        416 => {
            let _ = fs::remove_file(part);
            return Err("сервер не принял докачку — начнём заново".into());
        }
        code => return Err(format!("сервер ответил {code}")),
    };
    let mut buf = vec![0u8; 256 * 1024];
    loop {
        let n = resp.read(&mut buf).map_err(|e| format!("обрыв связи: {e}"))?;
        if n == 0 {
            break;
        }
        out.write_all(&buf[..n]).map_err(|e| e.to_string())?;
        if app::quitting() {
            return Err("программа закрывается".into());
        }
    }
    out.flush().map_err(|e| e.to_string())?;
    let got = fs::metadata(part).map(|m| m.len()).unwrap_or(0);
    if asset.size > 0 && got < asset.size {
        return Err(format!("соединение закрыто раньше времени ({got} из {} байт)", asset.size));
    }
    Ok(())
}

/// Переносная версия: zip → папка, в которой «TG Panel\TG Panel.exe».
fn unpack(zip_path: &Path, to: &Path) -> Result<PathBuf, String> {
    let _ = fs::remove_dir_all(to);
    let file = File::open(zip_path).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| format!("архив повреждён: {e}"))?;
    zip.extract(to).map_err(|e| format!("не удалось распаковать: {e}"))?;
    let stage = to.join("TG Panel");
    if !stage.join("TG Panel.exe").exists() {
        return Err("в архиве нет «TG Panel\\TG Panel.exe»".into());
    }
    Ok(stage)
}

/// Скачанное ранее обновление из state.json — если оно ещё нужно и файл цел.
fn pending(data: &Path) -> Option<Ready> {
    let state = load_state(data);
    let ready: Ready = serde_json::from_value(state.get("pending")?.clone()).ok()?;
    let usable = newer(&ready.version, VERSION)
        && !is_bad(data, &ready.version)
        && install_kind() == Some(ready.kind.as_str())
        && sha256_file(&ready.file).is_ok_and(|h| h == ready.sha256)
        && ready.stage.as_ref().is_none_or(|s| s.join("TG Panel.exe").exists());
    if usable {
        return Some(ready);
    }
    update_state(data, |s| {
        s.remove("pending");
    });
    if !newer(&ready.version, VERSION) {
        // уже стоит эта версия или новее — скачанное больше не нужно
        let _ = fs::remove_dir_all(data.join("update").join(&ready.version));
    }
    None
}

// ---------- установка ----------

fn on_ready(app: &AppHandle) {
    let Some(ready) = with(|s| s.ready.clone()) else { return };
    app::set_update_text(&format!("Установить {} и перезапустить", ready.version));
    if needs_admin() && app::setting("user_install_asked").is_none() {
        offer_user_install(app);
        return;
    }
    let manual = with(|s| s.manual);
    if manual && !app::main_visible() {
        install_now(app);
        return;
    }
    if app::main_visible() {
        app::show_update_banner(app, &ready.version);
    }
    // окно в трее — поставит idle_install, когда программа простоит минуту
}

/// Программа стоит «для всех» (Program Files): каждое обновление спрашивало бы права администратора.
/// Один раз предлагаем перейти на установку для текущего пользователя — дальше без вопросов.
fn offer_user_install(app: &AppHandle) {
    let app = app.clone();
    std::thread::spawn(move || {
        let text = format!(
            "Обновление TG Panel готово к установке.\n\nПрограмма установлена для всех пользователей ({}), поэтому \
             каждое обновление требует подтверждения администратора. Перейти на установку только для вас? Тогда \
             обновления будут ставиться сами, без запросов. Аккаунты и настройки сохранятся, старая копия будет \
             удалена — для этого Windows спросит разрешение один раз.",
            paths::app_dir().display()
        );
        let yes = app::ask_custom(&app, &text, "Перейти", "Не сейчас");
        app::set_setting("user_install_asked", if yes { "yes" } else { "no" });
        log::info!("Переход на установку для пользователя: {}", if yes { "согласие" } else { "отказ" });
        if yes {
            with(|s| s.to_user = true);
            install_now(&app);
        } else if app::main_visible() {
            if let Some(v) = with(|s| s.ready.as_ref().map(|r| r.version.clone())) {
                app::show_update_banner(&app, &v);
            }
        }
    });
}

pub fn tray_clicked(app: &AppHandle) {
    if with(|s| s.ready.is_some()) {
        install_now(app);
    } else {
        check(app, true);
    }
}

/// «Перезапустить»: выйти, поставить, запустить снова в том же состоянии окна (открыто или в трее).
pub fn install_now(app: &AppHandle) {
    if with(|s| s.ready.is_none()) {
        return;
    }
    let hidden = !app::main_visible();
    app::quit(app, After::Update { relaunch: true, hidden });
}

/// Окно в трее и программа простаивает — ставим тихо и возвращаемся в трей.
fn idle_install(app: &AppHandle) {
    let ready = with(|s| s.ready.is_some() && !s.busy);
    if !ready || !app::auto_update() || app::quitting() || app::downloads_active() {
        return;
    }
    // «для всех» без согласия на переход — ставить молча нельзя (окно UAC), только при выходе или по кнопке
    if needs_admin() && !with(|s| s.to_user) {
        return;
    }
    if app::hidden_for().is_some_and(|d| d >= IDLE_BEFORE_INSTALL) {
        log::info!("Окно в трее, программа простаивает — ставим обновление");
        install_now(app);
    }
}

pub fn has_ready() -> bool {
    with(|s| s.ready.is_some())
}

/// План для помощника обновления. None — ставить нечего.
pub fn plan(data: &Path, relaunch: bool, hidden: bool, stop_started_ms: u128) -> Option<crate::helper::Plan> {
    let (ready, to_user) = with(|s| (s.ready.clone(), s.to_user));
    let ready = ready?;
    Some(crate::helper::Plan {
        pid: std::process::id(),
        data_dir: data.to_path_buf(),
        app_dir: paths::app_dir(),
        kind: ready.kind,
        file: ready.file,
        stage: ready.stage,
        version: ready.version,
        prev_version: VERSION.to_string(),
        notes: ready.notes,
        relaunch,
        hidden,
        to_user,
        autostart: crate::autostart::enabled(),
        stop_started_ms,
    })
}

/// Обновление, скачанное в прошлый раз, при запуске: ставим сразу, пока ничего не запущено (автообновление).
/// true — помощник запущен, этой копии нужно выйти.
pub fn install_pending_at_start(data: &Path, hidden: bool) -> bool {
    let Some(ready) = pending(data) else { return false };
    if ready.kind == "setup" && needs_admin() {
        return false; // без согласия на переход — не при запуске (окно UAC вместо программы)
    }
    log::info!("При запуске: ставим скачанное ранее обновление {}", ready.version);
    with(|s| s.ready = Some(ready));
    let Some(plan) = plan(data, true, hidden, crate::helper::now_ms()) else { return false };
    match crate::helper::launch(data, &plan) {
        Ok(()) => true,
        Err(e) => {
            log::error!("Не удалось запустить установку обновления: {e}");
            false
        }
    }
}
