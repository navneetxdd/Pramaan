use std::ffi::{OsStr, OsString};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use tauri::{Manager, RunEvent};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::{process::CommandChild, ShellExt};

const ENGINE_URL: &str = "http://127.0.0.1:8787/api/v1/version";
const ENGINE_START_ATTEMPTS: u32 = 40;
const ENGINE_START_DELAY: Duration = Duration::from_millis(350);

enum EngineChild {
    #[cfg(debug_assertions)]
    Debug(std::process::Child),
    #[cfg(not(debug_assertions))]
    Release(CommandChild),
}

struct EngineProcess(Mutex<Option<EngineChild>>);

#[cfg(debug_assertions)]
fn repo_root() -> Result<PathBuf, String> {
    if let Some(root) = std::env::var_os("PRAMAAN_ROOT") {
        let root = PathBuf::from(root);
        if root.join("run.py").is_file() {
            return Ok(root);
        }
        return Err(format!(
            "PRAMAAN_ROOT does not contain run.py: {}",
            root.display()
        ));
    }

    let mut directory = std::env::current_exe()
        .map_err(|error| format!("Cannot locate the desktop executable: {error}"))?
        .parent()
        .map(PathBuf::from)
        .ok_or_else(|| "The desktop executable has no parent directory.".to_string())?;

    for _ in 0..8 {
        if directory.join("run.py").is_file()
            && directory
                .join("engine")
                .join("app")
                .join("main.py")
                .is_file()
        {
            return Ok(directory);
        }
        if !directory.pop() {
            break;
        }
    }

    Err("Cannot locate run.py. Set PRAMAAN_ROOT to the repository root.".to_string())
}

fn resolve_ffmpeg() -> Option<OsString> {
    let candidate = std::env::var_os("FORENSIC_FFMPEG")
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| OsString::from("ffmpeg"));

    let status = Command::new(&candidate)
        .arg("-version")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    match status {
        Ok(result) if result.success() => Some(candidate),
        Ok(result) => {
            eprintln!(
                "Pramaan: FFmpeg returned exit code {}. MP4 export will be unavailable until \
                 a licensed FFmpeg binary is on PATH or FORENSIC_FFMPEG is set.",
                result
                    .code()
                    .map_or_else(|| "unknown".to_string(), |code| code.to_string())
            );
            None
        }
        Err(error) => {
            eprintln!(
                "Pramaan: FFmpeg not found ({error}). MP4 export will be unavailable until \
                 ffmpeg.exe is on PATH or FORENSIC_FFMPEG points to a licensed binary."
            );
            None
        }
    }
}

#[cfg(debug_assertions)]
fn spawn_engine(_: &tauri::App, ffmpeg: Option<&OsStr>) -> Result<EngineChild, String> {
    let root = repo_root()?;
    let python = std::env::var_os("PRAMAAN_PYTHON").unwrap_or_else(|| {
        if cfg!(windows) {
            OsString::from("python")
        } else {
            OsString::from("python3")
        }
    });

    let mut command = Command::new(python);
    command
        .arg(root.join("run.py"))
        .current_dir(root)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    if let Some(path) = ffmpeg {
        command.env("FORENSIC_FFMPEG", path);
    }

    command
        .spawn()
        .map(EngineChild::Debug)
        .map_err(|error| format!("Could not launch the debug engine with run.py: {error}"))
}

#[cfg(not(debug_assertions))]
fn spawn_engine(app: &tauri::App, ffmpeg: Option<&OsStr>) -> Result<EngineChild, String> {
    let mut command = app
        .shell()
        .sidecar("pramaan-engine")
        .map_err(|error| format!("Could not resolve the packaged engine sidecar: {error}"))?;

    if let Some(path) = ffmpeg {
        command = command.env("FORENSIC_FFMPEG", path);
    }

    let (mut events, child) = command
        .spawn()
        .map_err(|error| format!("Could not launch the packaged engine sidecar: {error}"))?;

    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            match event {
                tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                    eprintln!("Pramaan engine: {}", String::from_utf8_lossy(&line));
                }
                tauri_plugin_shell::process::CommandEvent::Error(error) => {
                    eprintln!("Pramaan engine process error: {error}");
                }
                _ => {}
            }
        }
    });

    Ok(EngineChild::Release(child))
}

fn engine_is_ready() -> bool {
    ureq::get(ENGINE_URL)
        .call()
        .map(|response| response.status() == 200)
        .unwrap_or(false)
}

fn wait_for_engine() -> bool {
    for _ in 0..ENGINE_START_ATTEMPTS {
        if engine_is_ready() {
            return true;
        }
        thread::sleep(ENGINE_START_DELAY);
    }
    false
}

fn stop_engine(state: &EngineProcess) {
    let Ok(mut guard) = state.0.lock() else {
        return;
    };
    let Some(child) = guard.take() else {
        return;
    };

    match child {
        #[cfg(debug_assertions)]
        EngineChild::Debug(mut process) => {
            let _ = process.kill();
            let _ = process.wait();
        }
        #[cfg(not(debug_assertions))]
        EngineChild::Release(process) => {
            let _ = process.kill();
        }
    }
}

fn show_startup_error(app: &tauri::App, message: String) {
    let handle = app.handle().clone();
    app.dialog()
        .message(message)
        .title("Pramaan could not start")
        .kind(MessageDialogKind::Error)
        .show(move |_| handle.exit(1));
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .manage(EngineProcess(Mutex::new(None)))
        .setup(|app| {
            if engine_is_ready() {
                show_startup_error(
                    app,
                    "Port 8787 is already serving an engine. Close the other Pramaan \
                     instance before starting the desktop application."
                        .to_string(),
                );
                return Ok(());
            }

            let ffmpeg = resolve_ffmpeg();

            let child = match spawn_engine(app, ffmpeg.as_deref()) {
                Ok(child) => child,
                Err(error) => {
                    show_startup_error(app, error);
                    return Ok(());
                }
            };

            let state = app.state::<EngineProcess>();
            if let Ok(mut guard) = state.0.lock() {
                *guard = Some(child);
            } else {
                show_startup_error(
                    app,
                    "Could not initialize engine process state.".to_string(),
                );
                return Ok(());
            }

            if !wait_for_engine() {
                stop_engine(state.inner());
                show_startup_error(
                    app,
                    "The Pramaan engine did not become ready on 127.0.0.1:8787. \
                     Check the application logs and available disk space."
                        .to_string(),
                );
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build Pramaan desktop")
        .run(|app_handle, event| {
            if matches!(event, RunEvent::Exit) {
                if let Some(state) = app_handle.try_state::<EngineProcess>() {
                    stop_engine(state.inner());
                }
            }
        });
}
