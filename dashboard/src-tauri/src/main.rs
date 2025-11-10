// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Listener, Manager, State};

struct BackendProcess(Mutex<Option<Child>>);

fn start_backend_process(app_handle: &AppHandle) -> Option<Child> {
    #[cfg(target_os = "macos")]
    let backend_path = "astrbot-backend.app/Contents/MacOS/main";

    #[cfg(target_os = "windows")]
    let backend_path = "astrbot-backend.exe";

    #[cfg(target_os = "linux")]
    let backend_path = "astrbot-backend";

    // 获取资源目录
    let resource_dir = match app_handle
        .path()
        .resource_dir()
    {
        Ok(dir) => dir,
        Err(e) => {
            eprintln!("Failed to get resource directory: {}", e);
            return None;
        }
    };

    let full_backend_path = resource_dir.join(backend_path);

    println!("Starting backend process at: {:?}", full_backend_path);

    match Command::new(&full_backend_path).spawn() {
        Ok(child) => {
            println!(
                "Backend process started successfully with PID: {}",
                child.id()
            );
            Some(child)
        }
        Err(e) => {
            eprintln!("Failed to start backend process: {}", e);
            None
        }
    }
}

#[tauri::command]
fn restart_backend(
    app_handle: AppHandle,
    backend_state: State<BackendProcess>,
) -> Result<String, String> {
    let mut backend = backend_state.0.lock().unwrap();

    // 停止现有进程
    if let Some(mut child) = backend.take() {
        let _ = child.kill();
        let _ = child.wait();
    }

    // 启动新进程
    *backend = start_backend_process(&app_handle);

    if backend.is_some() {
        Ok("Backend restarted successfully".to_string())
    } else {
        Err("Failed to restart backend".to_string())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            // 启动后端进程
            let backend_process = start_backend_process(app.handle());
            app.manage(BackendProcess(Mutex::new(backend_process)));
            Ok(())
        })
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![restart_backend])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // 关闭窗口时清理后端进程
                if let Some(backend_state) = window.app_handle().try_state::<BackendProcess>() {
                    let mut backend = backend_state.0.lock().unwrap();
                    if let Some(mut child) = backend.take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn main() {
    run();
}

