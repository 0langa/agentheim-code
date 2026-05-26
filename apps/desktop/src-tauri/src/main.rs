use serde::Deserialize;
use std::env;
use std::fs;
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;

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
    let mut last_error = String::from("No Python launcher candidates were available.");
    for (program, prefix_args) in python_launchers() {
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
            .stdout(Stdio::null())
            .stderr(Stdio::null());
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
fn backend_url(state: tauri::State<'_, BackendState>) -> Result<Option<String>, String> {
    if let Ok(url) = env::var("AGENTHEIM_CODE_BACKEND_URL") {
        return Ok(Some(url));
    }

    let settings = launch_settings();
    let url = format!("http://127.0.0.1:{}", settings.port);
    if backend_is_ready(settings.port) {
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
        *child_guard = Some(start_backend(&settings.workspace, settings.port)?);
    }
    drop(child_guard);

    if wait_for_backend(settings.port) {
        return Ok(Some(url));
    }

    Err(format!(
        "Desktop backend did not become ready for workspace {}.",
        settings.workspace.display()
    ))
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
        .manage(state)
        .invoke_handler(tauri::generate_handler![backend_url])
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
