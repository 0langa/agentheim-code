use serde::Deserialize;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::ExitStatus;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

const DEFAULT_BACKEND_PORT: u16 = 8765;
const BACKEND_READY_TIMEOUT: Duration = Duration::from_secs(8);

#[derive(Debug, Default, Deserialize)]
struct DesktopConfig {
    core: Option<DesktopCoreConfig>,
}

#[derive(Debug, Default, Deserialize)]
struct DesktopCoreConfig {
    default_workspace: Option<String>,
    default_port: Option<u16>,
}

#[derive(Default)]
struct BackendState {
    child: Mutex<Option<Child>>,
    last_error: Mutex<Option<String>>,
}

#[derive(Debug)]
struct LaunchSettings {
    workspace: PathBuf,
    port: u16,
}

fn appdata_dir() -> Option<PathBuf> {
    env::var_os("APPDATA").map(PathBuf::from)
}

fn config_file() -> Option<PathBuf> {
    appdata_dir().map(|base| base.join("Agentheim Code").join("config.toml"))
}

fn load_config() -> DesktopConfig {
    let Some(path) = config_file() else {
        return DesktopConfig::default();
    };
    let Ok(contents) = fs::read_to_string(path) else {
        return DesktopConfig::default();
    };
    toml::from_str(&contents).unwrap_or_default()
}

fn home_dir() -> PathBuf {
    env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn resolve_workspace(config: &DesktopConfig) -> PathBuf {
    if let Some(value) = env::var_os("AGENTHEIM_CODE_WORKSPACE") {
        let path = PathBuf::from(value);
        if path.is_dir() {
            return path;
        }
    }

    if let Some(workspace) = config
        .core
        .as_ref()
        .and_then(|core| core.default_workspace.as_ref())
    {
        let path = PathBuf::from(workspace);
        if path.is_dir() {
            return path;
        }
        if path.is_relative() {
            let home_joined = home_dir().join(&path);
            if home_joined.is_dir() {
                return home_joined;
            }
        }
    }

    home_dir()
}

fn resolve_port(config: &DesktopConfig) -> u16 {
    env::var("AGENTHEIM_CODE_BACKEND_PORT")
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .or_else(|| config.core.as_ref().and_then(|core| core.default_port))
        .unwrap_or(DEFAULT_BACKEND_PORT)
}

fn backend_addr(port: u16) -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], port))
}

fn backend_is_ready(port: u16) -> bool {
    TcpStream::connect_timeout(&backend_addr(port), Duration::from_millis(250)).is_ok()
}

fn wait_for_backend(port: u16) -> bool {
    let deadline = Instant::now() + BACKEND_READY_TIMEOUT;
    while Instant::now() < deadline {
        if backend_is_ready(port) {
            return true;
        }
        thread::sleep(Duration::from_millis(150));
    }
    false
}

fn backend_log_path(workspace: &Path) -> PathBuf {
    workspace.join(".ai-team").join("backend.log")
}

fn prepare_backend_log(workspace: &Path) -> Result<PathBuf, String> {
    let log_path = backend_log_path(workspace);
    if let Some(parent) = log_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("Unable to create backend log directory {}: {error}", parent.display()))?;
    }
    Ok(log_path)
}

fn tail_backend_log(log_path: &Path) -> String {
    const MAX_BYTES: u64 = 8192;
    let Ok(mut file) = OpenOptions::new().read(true).open(log_path) else {
        return String::new();
    };
    let Ok(length) = file.metadata().map(|meta| meta.len()) else {
        return String::new();
    };
    let start = length.saturating_sub(MAX_BYTES);
    if file.seek(SeekFrom::Start(start)).is_err() {
        return String::new();
    }
    let mut text = String::new();
    if file.read_to_string(&mut text).is_err() {
        return String::new();
    }
    if start > 0 {
        if let Some((_, tail)) = text.split_once('\n') {
            return tail.trim().to_string();
        }
    }
    text.trim().to_string()
}

fn format_backend_failure(
    workspace: &Path,
    log_path: &Path,
    exit_status: Option<ExitStatus>,
) -> String {
    let mut message = match exit_status {
        Some(status) => format!(
            "Desktop backend failed to become ready for workspace {} (process exited with {}).",
            workspace.display(),
            status
        ),
        None => format!(
            "Desktop backend did not become ready for workspace {} within {} seconds.",
            workspace.display(),
            BACKEND_READY_TIMEOUT.as_secs()
        ),
    };
    let tail = tail_backend_log(log_path);
    if !tail.is_empty() {
        message.push_str(&format!(
            " Backend log tail ({}):\n{}",
            log_path.display(),
            tail
        ));
    } else {
        message.push_str(&format!(
            " No backend log output was captured at {}.",
            log_path.display()
        ));
    }
    message
}

fn python_launchers() -> Vec<(String, Vec<String>)> {
    let mut launchers = Vec::new();
    if let Ok(command) = env::var("AGENTHEIM_CODE_PYTHON") {
        launchers.push((command, Vec::new()));
    }
    if cfg!(target_os = "windows") {
        launchers.push(("py".into(), vec!["-3".into()]));
    }
    launchers.push(("python".into(), Vec::new()));
    launchers.push(("python3".into(), Vec::new()));
    launchers
}

#[cfg(target_os = "windows")]
fn hide_window(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(0x08000000);
}

#[cfg(not(target_os = "windows"))]
fn hide_window(_command: &mut Command) {}

fn start_backend(workspace: &Path, port: u16) -> Result<Child, String> {
    let log_path = prepare_backend_log(workspace)?;
    let mut last_error = String::from("No Python launcher candidates were available.");
    for (program, prefix_args) in python_launchers() {
        let log_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .map_err(|error| format!("Unable to open backend log {}: {error}", log_path.display()))?;
        let stderr_file = log_file
            .try_clone()
            .map_err(|error| format!("Unable to clone backend log handle {}: {error}", log_path.display()))?;
        let mut command = Command::new(&program);
        hide_window(&mut command);
        command
            .args(prefix_args)
            .arg("-m")
            .arg("agentheim_code._serve")
            .arg(workspace)
            .arg(port.to_string())
            .current_dir(workspace)
            .stdin(Stdio::null())
            .stdout(Stdio::from(log_file))
            .stderr(Stdio::from(stderr_file));
        match command.spawn() {
            Ok(child) => return Ok(child),
            Err(error) => {
                last_error = format!("{program}: {error}");
            }
        }
    }
    Err(format!(
        "Unable to start the Python backend automatically. Last error: {last_error}"
    ))
}

fn launch_settings() -> LaunchSettings {
    let config = load_config();
    LaunchSettings {
        workspace: resolve_workspace(&config),
        port: resolve_port(&config),
    }
}

#[tauri::command]
fn desktop_pick_workspace(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let selection = app
        .dialog()
        .file()
        .set_title("Choose workspace")
        .blocking_pick_folder();
    let Some(path) = selection else {
        return Ok(None);
    };
    let path = path
        .into_path()
        .map_err(|_| String::from("Selected workspace path is not available."))?;
    Ok(Some(path.to_string_lossy().to_string()))
}

#[tauri::command]
fn backend_launch_error(state: tauri::State<'_, BackendState>) -> Result<Option<String>, String> {
    let error = state
        .last_error
        .lock()
        .map_err(|_| String::from("Desktop backend error state is unavailable."))?;
    Ok(error.clone())
}

#[tauri::command]
fn backend_url(state: tauri::State<'_, BackendState>) -> Result<Option<String>, String> {
    if let Ok(url) = env::var("AGENTHEIM_CODE_BACKEND_URL") {
        return Ok(Some(url));
    }

    let settings = launch_settings();
    let url = format!("http://127.0.0.1:{}", settings.port);
    if backend_is_ready(settings.port) {
        if let Ok(mut error) = state.last_error.lock() {
            *error = None;
        }
        return Ok(Some(url));
    }

    let mut child_guard = state
        .child
        .lock()
        .map_err(|_| String::from("Desktop backend state is unavailable."))?;

    let should_spawn = match child_guard.as_mut() {
        Some(child) => child.try_wait().map_err(|error| error.to_string())?.is_some(),
        None => true,
    };

    if should_spawn {
        match start_backend(&settings.workspace, settings.port) {
            Ok(child) => {
                *child_guard = Some(child);
                if let Ok(mut error) = state.last_error.lock() {
                    *error = None;
                }
            }
            Err(error) => {
                if let Ok(mut last_error) = state.last_error.lock() {
                    *last_error = Some(error.clone());
                }
                return Err(error);
            }
        }
    }
    drop(child_guard);

    if wait_for_backend(settings.port) {
        if let Ok(mut error) = state.last_error.lock() {
            *error = None;
        }
        return Ok(Some(url));
    }

    let exit_status = {
        let mut child_guard = state
            .child
            .lock()
            .map_err(|_| String::from("Desktop backend state is unavailable."))?;
        match child_guard.as_mut() {
            Some(child) => child.try_wait().map_err(|error| error.to_string())?,
            None => None,
        }
    };
    let log_path = backend_log_path(&settings.workspace);
    let message = format_backend_failure(&settings.workspace, &log_path, exit_status);
    if let Ok(mut error) = state.last_error.lock() {
        *error = Some(message.clone());
    }
    Err(message)
}

fn stop_backend(state: &BackendState) {
    let Ok(mut child_guard) = state.child.lock() else {
        return;
    };
    let Some(mut child) = child_guard.take() else {
        return;
    };
    if let Ok(None) = child.try_wait() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let state = BackendState::default();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(state)
        .invoke_handler(tauri::generate_handler![backend_url, desktop_pick_workspace, backend_launch_error])
        .build(tauri::generate_context!())
        .expect("error while building Agentheim Code");

    app.run(|app_handle, event| match event {
            tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. } => {
                let state = app_handle.state::<BackendState>();
                stop_backend(state.inner());
            }
            _ => {}
        });
}

fn main() {
    run();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_config_values() {
        let config: DesktopConfig = toml::from_str(
            r#"
[core]
default_workspace = "C:\\work\\repo"
default_port = 9999
"#,
        )
        .expect("config should parse");

        let core = config.core.expect("core section");
        assert_eq!(core.default_workspace.as_deref(), Some("C:\\work\\repo"));
        assert_eq!(core.default_port, Some(9999));
    }

    #[test]
    fn backend_address_uses_default_host() {
        assert_eq!(backend_addr(8765), "127.0.0.1:8765".parse().unwrap());
    }
}
