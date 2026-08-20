#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::Value;

const DEFAULT_PORT: u16 = 8765;

#[derive(Clone, Serialize)]
struct Handshake {
    url: String,
    nonce: String,
    os_identity: String,
}

struct AppState {
    handshake: Mutex<Option<Handshake>>,
}

fn os_identity() -> String {
    std::env::var("USERNAME")
        .or_else(|_| std::env::var("USER"))
        .unwrap_or_else(|_| "unknown-operator".to_string())
}

fn loopback_open(port: u16) -> bool {
    TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_millis(250)).is_ok()
}

fn handshake_path() -> PathBuf {
    let mut dir = std::env::temp_dir();
    dir.push(format!("pp-cc-handshake-{}.json", std::process::id()));
    dir
}

fn read_handshake(path: &Path) -> Result<Handshake, String> {
    let raw = fs::read_to_string(path).map_err(|error| error.to_string())?;
    let value: Value = serde_json::from_str(&raw).map_err(|error| error.to_string())?;
    Ok(Handshake {
        url: value
            .get("url")
            .and_then(Value::as_str)
            .ok_or("handshake missing url")?
            .to_string(),
        nonce: value
            .get("nonce")
            .and_then(Value::as_str)
            .ok_or("handshake missing nonce")?
            .to_string(),
        os_identity: value
            .get("os_identity")
            .and_then(Value::as_str)
            .unwrap_or(&os_identity())
            .to_string(),
    })
}

fn spawn_loopback_service(root: &str, handshake: &Path) -> Result<(), String> {
    let python = std::env::var("PROJECT_PIPELINE_PYTHON").unwrap_or_else(|_| "python".to_string());
    let mut command = Command::new(python);
    command
        .args([
            "-B",
            "-m",
            "project_pipeline",
            "command-center",
            "serve",
            "--root",
            root,
            "--host",
            "127.0.0.1",
            "--port",
            &DEFAULT_PORT.to_string(),
            "--handshake-file",
            handshake.to_str().ok_or("handshake path is not unicode")?,
        ])
        .env("PYTHONPATH", "src")
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command.spawn().map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
fn desktop_os_identity() -> String {
    os_identity()
}

#[tauri::command]
fn service_running() -> bool {
    loopback_open(DEFAULT_PORT)
}

#[tauri::command]
fn start_or_attach_service(
    state: tauri::State<AppState>,
    root: Option<String>,
) -> Result<Handshake, String> {
    let repo = root.unwrap_or_else(|| {
        std::env::var("PROJECT_PIPELINE_ROOT").unwrap_or_else(|_| String::from("."))
    });
    if !loopback_open(DEFAULT_PORT) {
        let path = handshake_path();
        let _ = fs::remove_file(&path);
        spawn_loopback_service(&repo, &path)?;
        let deadline = Instant::now() + Duration::from_secs(20);
        while Instant::now() < deadline {
            if path.is_file() && loopback_open(DEFAULT_PORT) {
                break;
            }
            thread::sleep(Duration::from_millis(100));
        }
        let handshake = read_handshake(&path)?;
        *state.handshake.lock().map_err(|error| error.to_string())? = Some(handshake.clone());
        return Ok(handshake);
    }
    if let Some(existing) = state
        .handshake
        .lock()
        .map_err(|error| error.to_string())?
        .clone()
    {
        return Ok(existing);
    }
    Err("loopback service is running but no unused handshake remains; restart the service".into())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .manage(AppState {
            handshake: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            desktop_os_identity,
            service_running,
            start_or_attach_service
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Project Pipeline Command Center");
}
