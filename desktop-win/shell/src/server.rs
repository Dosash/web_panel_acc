//! Локальный режим: серверная часть (`server\tg-panel-server.exe`, см. desktop-win/server/main.py) отдельным
//! процессом. Готовность и ошибки — строками JSON из её stdout, журнал — из stderr в tg-panel.log.
//! Выход: «quit» в stdin, затем ждём, пока панель отключит аккаунты; принудительно — только после таймаута.

use std::io::{BufRead, BufReader, Write};
use std::os::windows::process::CommandExt;
use std::path::Path;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::logger;
use crate::paths;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
pub const STOP_TIMEOUT: Duration = Duration::from_secs(15);

pub enum Event {
    Ready { port: u16, cookie: (String, String) },
    Error(String),
    /// процесс завершился (код выхода) — сам, не по просьбе оболочки
    Exited(Option<i32>),
}

pub struct LocalServer {
    child: Arc<Mutex<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    stopping: Arc<std::sync::atomic::AtomicBool>,
}

impl LocalServer {
    pub fn start(data: &Path, port: u16, on_event: impl Fn(Event) + Send + Sync + 'static) -> std::io::Result<Self> {
        let cmd = paths::server_command();
        let mut command = Command::new(&cmd[0]);
        command
            .args(&cmd[1..])
            .arg("--data")
            .arg(data)
            .args(if port > 0 { vec!["--port".to_string(), port.to_string()] } else { vec![] })
            .current_dir(data)
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .env_remove("TG_PANEL_DATA")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .creation_flags(CREATE_NO_WINDOW);
        let mut child = command.spawn()?;
        log::info!("Серверная часть запущена (pid {}): {}", child.id(), cmd[0].display());
        let stdout = child.stdout.take().expect("stdout");
        let stderr = child.stderr.take().expect("stderr");
        let stdin = child.stdin.take();
        let on_event = Arc::new(on_event);

        let events = on_event.clone();
        std::thread::Builder::new().name("server-stdout".into()).spawn(move || {
            for line in read_lines(stdout) {
                if !line.starts_with('{') {
                    if !line.trim().is_empty() {
                        logger::write_raw(&line);
                    }
                    continue;
                }
                // в строке готовности — cookie входа: в журнал её не пишем
                match serde_json::from_str::<serde_json::Value>(&line) {
                    Ok(v) if v["event"] == "ready" => {
                        let port = v["port"].as_u64().unwrap_or(0) as u16;
                        let cookie = (
                            v["cookie"][0].as_str().unwrap_or_default().to_string(),
                            v["cookie"][1].as_str().unwrap_or_default().to_string(),
                        );
                        log::info!("Сервер панели готов: порт {port}");
                        events(Event::Ready { port, cookie });
                    }
                    Ok(v) if v["event"] == "error" => {
                        let msg = v["message"].as_str().unwrap_or("неизвестная ошибка").to_string();
                        log::error!("Сервер панели: {msg}");
                        events(Event::Error(msg));
                    }
                    _ => logger::write_raw(&line), // это не наша строка — просто в журнал
                }
            }
        })?;
        std::thread::Builder::new().name("server-stderr".into()).spawn(move || {
            for line in read_lines(stderr) {
                if !line.trim().is_empty() {
                    logger::write_raw(&line);
                }
            }
        })?;

        let child = Arc::new(Mutex::new(child));
        let stopping = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let (watch, stop_flag) = (child.clone(), stopping.clone());
        std::thread::Builder::new().name("server-wait".into()).spawn(move || loop {
            std::thread::sleep(Duration::from_millis(250));
            let status = watch.lock().unwrap_or_else(|e| e.into_inner()).try_wait();
            match status {
                Ok(None) => continue,
                Ok(Some(status)) => {
                    if !stop_flag.load(std::sync::atomic::Ordering::SeqCst) {
                        log::warn!("Серверная часть завершилась сама: {status}");
                        on_event(Event::Exited(status.code()));
                    }
                    return;
                }
                Err(_) => return,
            }
        })?;
        Ok(LocalServer { child, stdin: Mutex::new(stdin), stopping })
    }

    /// Штатная остановка: аккаунты и боты отключаются в lifespan панели. Возвращает, сколько заняло.
    pub fn stop(&self, timeout: Duration) -> Duration {
        let started = Instant::now();
        self.stopping.store(true, std::sync::atomic::Ordering::SeqCst);
        if let Some(mut stdin) = self.stdin.lock().unwrap_or_else(|e| e.into_inner()).take() {
            let _ = stdin.write_all(b"quit\n");
            let _ = stdin.flush();
        } // stdin закрывается здесь — и это тоже сигнал выхода
        loop {
            let mut child = self.child.lock().unwrap_or_else(|e| e.into_inner());
            match child.try_wait() {
                Ok(Some(status)) => {
                    log::info!("Сервер панели остановлен за {:.1} с ({status})", started.elapsed().as_secs_f32());
                    break;
                }
                Ok(None) if started.elapsed() < timeout => {}
                _ => {
                    log::warn!("Сервер панели не остановился за {} с — завершаем принудительно", timeout.as_secs());
                    let _ = child.kill();
                    let _ = child.wait();
                    break;
                }
            }
            drop(child);
            std::thread::sleep(Duration::from_millis(50));
        }
        started.elapsed()
    }
}

/// Строки из канала: байты как есть, UTF-8 с заменой битых символов.
fn read_lines(r: impl std::io::Read) -> impl Iterator<Item = String> {
    let mut reader = BufReader::new(r);
    std::iter::from_fn(move || {
        let mut buf = Vec::new();
        match reader.read_until(b'\n', &mut buf) {
            Ok(0) | Err(_) => None,
            Ok(_) => Some(String::from_utf8_lossy(&buf).trim_end_matches(['\r', '\n']).to_string()),
        }
    })
}
