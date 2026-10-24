//! Помощник обновления. Программа копирует себя в `<данные>\update\helper\tg-panel-update.exe` (файлы в папке
//! программы будут заменены) и запускает копию с `--apply-update <plan.json>`, а сама выходит. Помощник:
//!   1. ждёт выхода программы (сервер к этому времени уже остановлен штатно — аккаунты отключены);
//!   2. копирует папку программы в `<данные>\update\backup` (для отката);
//!   3. ставит: setup.exe /VERYSILENT (папку и ярлыки Inno Setup помнит) или файлы переносной версии поверх;
//!   4. запускает новую версию и ждёт отметку `<данные>\update\health-<версия>` («ok» — окно и сервер поднялись);
//!      если версия упала или не запустила сервер — возвращает прежние файлы, запускает прежнюю версию
//!      и записывает версию в state.json → bad (больше не ставится);
//!   5. при установке «на выходе» (без перезапуска) проверяет новые файлы без окна: `--check` и self-test сервера.
//! Пишет в тот же журнал tg-panel.log.

use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::json;
use windows::core::{HSTRING, PCWSTR};
use windows::Win32::Foundation::{CloseHandle, WAIT_OBJECT_0};
use windows::Win32::System::Threading::{GetExitCodeProcess, OpenProcess, WaitForSingleObject, INFINITE, PROCESS_SYNCHRONIZE};
use windows::Win32::UI::Shell::{ShellExecuteExW, SEE_MASK_NOCLOSEPROCESS, SHELLEXECUTEINFOW};

use crate::logger;
use crate::paths;
use crate::updater;
use crate::winreg::{self, HKCU};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const DETACHED_PROCESS: u32 = 0x0000_0008;
const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
const CREATE_BREAKAWAY_FROM_JOB: u32 = 0x0100_0000;
/// сколько ждать, пока новая версия поднимет окно и сервер (импорт панели — несколько секунд)
const HEALTH_TIMEOUT: Duration = Duration::from_secs(120);
const UNINSTALL_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{6E0B6C2A-3F4D-4E8B-9C1A-7D52A1F0B7E4}_is1";

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Plan {
    pub pid: u32,
    pub data_dir: PathBuf,
    pub app_dir: PathBuf,
    pub kind: String,
    pub file: PathBuf,
    pub stage: Option<PathBuf>,
    pub version: String,
    pub prev_version: String,
    pub notes: String,
    pub relaunch: bool,
    pub hidden: bool,
    /// установка «для всех» → для текущего пользователя (/CURRENTUSER), прежняя копия удаляется
    pub to_user: bool,
    pub autostart: bool,
    /// когда программа начала выходить (мс с 1970) — для подсчёта простоя
    pub stop_started_ms: u128,
}

pub fn now_ms() -> u128 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis()
}

pub fn health_path(data: &Path, version: &str) -> PathBuf {
    data.join("update").join(format!("health-{version}"))
}

/// Запуск помощника из программы (она сразу после этого выходит).
pub fn launch(data: &Path, plan: &Plan) -> Result<(), String> {
    let dir = data.join("update").join("helper");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let mut exe = dir.join("tg-panel-update.exe");
    if std::fs::copy(paths::exe(), &exe).is_err() {
        // прежний помощник ещё не вышел — своя копия рядом
        exe = dir.join(format!("tg-panel-update-{}.exe", std::process::id()));
        std::fs::copy(paths::exe(), &exe).map_err(|e| format!("не удалось скопировать помощника: {e}"))?;
    }
    let plan_path = data.join("update").join("plan.json");
    std::fs::write(&plan_path, serde_json::to_vec_pretty(plan).unwrap_or_default()).map_err(|e| e.to_string())?;
    spawn_detached(&exe, &[OsArg::from("--apply-update"), OsArg::from(plan_path.as_os_str())])
        .map_err(|e| format!("не удалось запустить помощника: {e}"))?;
    log::info!("Помощник обновления запущен: {} → {}", plan.prev_version, plan.version);
    Ok(())
}

type OsArg = std::ffi::OsString;

/// Процесс, который переживёт выход программы (и задание Windows, если программа в нём).
pub fn spawn_detached(exe: &Path, args: &[OsArg]) -> std::io::Result<std::process::Child> {
    let base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP;
    let run = |flags| {
        Command::new(exe)
            .args(args)
            .current_dir(exe.parent().unwrap_or(Path::new(".")))
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(flags)
            .spawn()
    };
    run(base | CREATE_BREAKAWAY_FROM_JOB).or_else(|_| run(base))
}

pub fn wait_pid(pid: u32, timeout: Duration) -> bool {
    unsafe {
        let Ok(handle) = OpenProcess(PROCESS_SYNCHRONIZE, false, pid) else { return true };
        let done = WaitForSingleObject(handle, timeout.as_millis() as u32) == WAIT_OBJECT_0;
        let _ = CloseHandle(handle);
        done
    }
}

struct Log<'a>(&'a Path);

impl Log<'_> {
    fn info(&self, msg: &str) {
        logger::append(self.0, "desktop.update", "INFO", msg);
    }
    fn error(&self, msg: &str) {
        logger::append(self.0, "desktop.update", "ERROR", msg);
    }
}

/// robocopy: копирование папки программы без папки данных переносной версии. Код < 8 — успех.
fn robocopy(from: &Path, to: &Path, mirror: bool, exclude: &Path) -> Result<(), String> {
    let mut cmd = Command::new("robocopy");
    cmd.arg(from).arg(to).arg(if mirror { "/MIR" } else { "/E" });
    cmd.args(["/R:3", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD"]).arg(exclude);
    let status = cmd.creation_flags(CREATE_NO_WINDOW).status().map_err(|e| format!("robocopy: {e}"))?;
    match status.code() {
        Some(c) if c < 8 => Ok(()),
        c => Err(format!("robocopy завершился с кодом {c:?}")),
    }
}

/// Запуск с правами администратора (окно UAC) и ожидание. Код выхода или None, если отказались.
fn run_elevated(exe: &Path, params: &str) -> Option<u32> {
    let (verb, file, params) = (HSTRING::from("runas"), HSTRING::from(exe.as_os_str()), HSTRING::from(params));
    let mut info = SHELLEXECUTEINFOW {
        cbSize: std::mem::size_of::<SHELLEXECUTEINFOW>() as u32,
        fMask: SEE_MASK_NOCLOSEPROCESS,
        lpVerb: PCWSTR(verb.as_ptr()),
        lpFile: PCWSTR(file.as_ptr()),
        lpParameters: PCWSTR(params.as_ptr()),
        nShow: 0,
        ..Default::default()
    };
    unsafe {
        ShellExecuteExW(&mut info).ok()?;
        if info.hProcess.is_invalid() {
            return Some(0);
        }
        WaitForSingleObject(info.hProcess, INFINITE);
        let mut code = 0u32;
        let _ = GetExitCodeProcess(info.hProcess, &mut code);
        let _ = CloseHandle(info.hProcess);
        Some(code)
    }
}

/// Команда с таймаутом: Some(код) или None, если не уложилась (процесс завершаем).
fn run_with_timeout(exe: &Path, args: &[&str], timeout: Duration) -> Option<i32> {
    let mut child = Command::new(exe).args(args).creation_flags(CREATE_NO_WINDOW)
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).spawn().ok()?;
    let started = Instant::now();
    loop {
        if let Ok(Some(status)) = child.try_wait() {
            return Some(status.code().unwrap_or(-1));
        }
        if started.elapsed() > timeout {
            let _ = child.kill();
            return None;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

enum Outcome {
    Ok,
    /// установка не прошла — файлы могли измениться, откатываем; bad — больше эту версию не ставить
    Failed { reason: String, bad: bool },
    /// установку отменили (например, отказались в окне UAC) — ничего не менялось
    Cancelled(String),
}

pub fn run(plan_path: &str) -> i32 {
    let Ok(plan) = std::fs::read(plan_path).map_err(|e| e.to_string()).and_then(|b| serde_json::from_slice::<Plan>(&b).map_err(|e| e.to_string())) else {
        return 2;
    };
    let data = plan.data_dir.clone();
    let log = Log(&data);
    log.info(&format!("Помощник обновления: {} → {} ({}{})", plan.prev_version, plan.version, plan.kind,
        if plan.to_user { ", переход на установку для пользователя" } else { "" }));
    if !wait_pid(plan.pid, Duration::from_secs(90)) {
        log.error("Программа не закрылась за 90 с — обновление отложено");
        return 1;
    }
    let started = Instant::now();
    let backup = data.join("update").join("backup");
    let portable_data = plan.app_dir.join("data");
    if !plan.to_user {
        let _ = std::fs::remove_dir_all(&backup);
        if let Err(e) = robocopy(&plan.app_dir, &backup, true, &portable_data) {
            log.error(&format!("Не удалось сохранить копию для отката ({e}) — обновление не ставим"));
            relaunch_old(&plan, &log);
            return 1;
        }
    }

    let (outcome, new_exe) = install(&plan, &log);
    let outcome = match outcome {
        Outcome::Ok => verify(&plan, &new_exe, &log),
        other => other,
    };
    match outcome {
        Outcome::Ok => {
            log.info(&format!("Обновление до {} установлено и запущено за {:.1} с", plan.version, started.elapsed().as_secs_f32()));
            updater::update_state(&data, |s| {
                s.remove("pending");
                s.insert("updated".into(), json!({"from": plan.prev_version, "to": plan.version}));
            });
            let _ = std::fs::remove_dir_all(&backup);
            let _ = std::fs::remove_dir_all(data.join("update").join(&plan.version));
            if plan.to_user {
                remove_all_users_copy(&plan, &new_exe, &log);
            }
            0
        }
        Outcome::Cancelled(reason) => {
            log.error(&format!("Обновление до {} отменено: {reason}", plan.version));
            relaunch_old(&plan, &log);
            1
        }
        Outcome::Failed { reason, bad } => {
            log.error(&format!("Обновление до {} не удалось: {reason} — возвращаем {}", plan.version, plan.prev_version));
            rollback(&plan, &backup, &log);
            updater::update_state(&data, |s| {
                s.remove("pending");
                if bad {
                    let mut list = s.get("bad").and_then(|v| v.as_array().cloned()).unwrap_or_default();
                    if !list.iter().any(|v| v == plan.version.as_str()) {
                        list.push(json!(plan.version));
                    }
                    s.insert("bad".into(), json!(list));
                }
                s.insert("rolled_back".into(), json!({"version": plan.version, "reason": reason, "to": plan.prev_version}));
            });
            if bad {
                let _ = std::fs::remove_dir_all(data.join("update").join(&plan.version));
            }
            relaunch_old(&plan, &log);
            1
        }
    }
}

fn install(plan: &Plan, log: &Log) -> (Outcome, PathBuf) {
    let old_exe = plan.app_dir.join("TG Panel.exe");
    if plan.kind == "portable" {
        let Some(stage) = &plan.stage else {
            return (Outcome::Failed { reason: "нет распакованных файлов".into(), bad: false }, old_exe);
        };
        // прежняя серверная часть целиком: в новой могли исчезнуть файлы (dist-info старых версий мешали бы)
        let _ = std::fs::remove_dir_all(plan.app_dir.join("server"));
        let _ = std::fs::remove_dir_all(plan.app_dir.join("_internal")); // от программы на PyQt5
        return match robocopy(stage, &plan.app_dir, false, &plan.app_dir.join("data")) {
            Ok(()) => (Outcome::Ok, old_exe),
            Err(e) => (Outcome::Failed { reason: e, bad: false }, old_exe),
        };
    }
    let setup_log = plan.data_dir.join("update").join("setup.log");
    let mut args = vec![
        "/VERYSILENT".to_string(), "/SUPPRESSMSGBOXES".into(), "/NORESTART".into(), "/NOCANCEL".into(), "/SP-".into(),
        format!("/LOG={}", setup_log.display()),
    ];
    if plan.to_user {
        args.push("/CURRENTUSER".into());
    }
    log.info(&format!("Установка: {} /VERYSILENT", plan.file.display()));
    let code = Command::new(&plan.file).args(&args).status().map(|s| s.code().unwrap_or(-1));
    let new_exe = if plan.to_user { user_install_exe() } else { old_exe };
    match code {
        Ok(0) => (Outcome::Ok, new_exe),
        // 2 — отменили (в том числе окно UAC), 5 — отказались продолжать: файлы не менялись
        Ok(2) | Ok(5) => (Outcome::Cancelled(format!("установщик отменён (код {})", code.unwrap_or(0))), new_exe),
        Ok(c) => (Outcome::Failed { reason: format!("установщик завершился с кодом {c}, журнал: {}", setup_log.display()), bad: false }, new_exe),
        Err(e) => (Outcome::Failed { reason: format!("установщик не запустился: {e}"), bad: false }, new_exe),
    }
}

fn user_install_exe() -> PathBuf {
    winreg::get_string(HKCU, UNINSTALL_KEY, "InstallLocation")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(std::env::var_os("LOCALAPPDATA").unwrap_or_default()).join("Programs").join("TG Panel"))
        .join("TG Panel.exe")
}

/// Новая версия работает? С перезапуском — по отметке здоровья; без — проверкой файлов без окна.
fn verify(plan: &Plan, exe: &Path, log: &Log) -> Outcome {
    if !plan.relaunch {
        if run_with_timeout(exe, &["--check"], Duration::from_secs(30)) != Some(0) {
            return Outcome::Failed { reason: "новая программа не запускается (--check)".into(), bad: true };
        }
        let server = exe.parent().unwrap_or(Path::new(".")).join("server").join("tg-panel-server.exe");
        return match run_with_timeout(&server, &["--self-test"], Duration::from_secs(180)) {
            Some(0) => Outcome::Ok,
            other => Outcome::Failed { reason: format!("серверная часть не проходит самопроверку (код {other:?})"), bad: true },
        };
    }
    let health = health_path(&plan.data_dir, &plan.version);
    let _ = std::fs::remove_file(&health);
    let mut args: Vec<OsArg> = vec!["--updated-from".into(), plan.prev_version.clone().into(),
        "--update-started".into(), plan.stop_started_ms.to_string().into()];
    if plan.hidden {
        args.insert(0, "--hidden".into());
    }
    let mut child = match spawn_detached(exe, &args) {
        Ok(c) => c,
        Err(e) => return Outcome::Failed { reason: format!("новая версия не запускается: {e}"), bad: true },
    };
    log.info(&format!("Новая версия запущена (pid {}), ждём, пока она поднимется", child.id()));
    let started = Instant::now();
    loop {
        if let Ok(text) = std::fs::read_to_string(&health) {
            let text = text.trim();
            if text == "ok" {
                let _ = std::fs::remove_file(&health);
                return Outcome::Ok;
            }
            if let Some(reason) = text.strip_prefix("fail:") {
                let _ = std::fs::remove_file(&health);
                let _ = wait_pid(child.id(), Duration::from_secs(20));
                let _ = child.kill();
                return Outcome::Failed { reason: format!("новая версия не запустилась: {}", reason.trim()), bad: true };
            }
        }
        if let Ok(Some(status)) = child.try_wait() {
            std::thread::sleep(Duration::from_millis(500));
            if std::fs::read_to_string(&health).is_ok_and(|t| t.trim() == "ok") {
                return Outcome::Ok; // успела отметиться и вышла (пользователь сразу закрыл)
            }
            return Outcome::Failed { reason: format!("новая версия завершилась через {:.0} с после запуска ({status})", started.elapsed().as_secs_f32()), bad: true };
        }
        if started.elapsed() > HEALTH_TIMEOUT {
            log.info("Новая версия работает, хотя не отметилась вовремя — считаем, что всё в порядке");
            return Outcome::Ok;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
}

fn rollback(plan: &Plan, backup: &Path, log: &Log) {
    if plan.to_user {
        // прежняя копия «для всех» не тронута; новую (для пользователя) убираем её деинсталлятором
        if let Some(uninstall) = winreg::get_string(HKCU, UNINSTALL_KEY, "InstallLocation").map(|d| PathBuf::from(d).join("unins000.exe")) {
            let _ = run_with_timeout(&uninstall, &["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], Duration::from_secs(120));
        }
        return;
    }
    let exclude = plan.app_dir.join("data");
    if robocopy(backup, &plan.app_dir, true, &exclude).is_ok() {
        log.info(&format!("Прежняя версия {} восстановлена", plan.prev_version));
        return;
    }
    // папка «для всех» (Program Files) — восстановить можно только с правами администратора
    let params = format!(
        "\"{}\" \"{}\" /MIR /R:3 /W:1 /NFL /NDL /NJH /NJS /NP /XD \"{}\"",
        backup.display(), plan.app_dir.display(), exclude.display()
    );
    match run_elevated(Path::new("robocopy"), &params) {
        Some(c) if c < 8 => log.info(&format!("Прежняя версия {} восстановлена (с правами администратора)", plan.prev_version)),
        other => log.error(&format!("Не удалось вернуть прежнюю версию (robocopy {other:?}) — переустановите программу")),
    }
}

fn relaunch_old(plan: &Plan, log: &Log) {
    if !plan.relaunch {
        return;
    }
    let exe = plan.app_dir.join("TG Panel.exe");
    let args: Vec<OsArg> = if plan.hidden { vec!["--hidden".into()] } else { vec![] };
    if let Err(e) = spawn_detached(&exe, &args) {
        log.error(&format!("Не удалось запустить {}: {e}", exe.display()));
    }
}

/// После перехода на установку для пользователя: удалить копию «для всех» (окно UAC один раз)
/// и вернуть автозапуск — деинсталлятор его убирает.
fn remove_all_users_copy(plan: &Plan, new_exe: &Path, log: &Log) {
    let uninstaller = plan.app_dir.join("unins000.exe");
    if uninstaller.exists() {
        match run_elevated(&uninstaller, "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART") {
            Some(0) => log.info(&format!("Копия для всех пользователей удалена: {}", plan.app_dir.display())),
            Some(c) => log.error(&format!("Деинсталлятор прежней копии завершился с кодом {c}")),
            None => log.error("Удаление прежней копии отменено — её можно удалить в «Приложениях» Windows"),
        }
    }
    if plan.autostart {
        let cmd = format!("\"{}\" --hidden", new_exe.display());
        let _ = winreg::set_string(HKCU, r"Software\Microsoft\Windows\CurrentVersion\Run", paths::APP_NAME, &cmd);
    }
}
