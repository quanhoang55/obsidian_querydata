use std::{net::TcpListener, sync::Mutex};

use tauri::{Manager, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct BackendState {
    url: String,
    child: Mutex<Option<CommandChild>>,
}

#[tauri::command]
fn backend_url(state: State<'_, BackendState>) -> String {
    state.url.clone()
}

fn available_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|error| error.to_string())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| error.to_string())
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            let port = available_port()?;
            let command = app
                .shell()
                .sidecar("obsidianquery-backend")?
                .env("OBSIDIANQUERY_PORT", port.to_string());
            let (mut events, child) = command.spawn()?;
            tauri::async_runtime::spawn(async move {
                while let Some(event) = events.recv().await {
                    match event {
                        tauri_plugin_shell::process::CommandEvent::Stdout(bytes) => {
                            println!("[backend] {}", String::from_utf8_lossy(&bytes));
                        }
                        tauri_plugin_shell::process::CommandEvent::Stderr(bytes) => {
                            eprintln!("[backend] {}", String::from_utf8_lossy(&bytes));
                        }
                        _ => {}
                    }
                }
            });
            app.manage(BackendState {
                url: format!("http://127.0.0.1:{port}"),
                child: Mutex::new(Some(child)),
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build ObsidianQuery");

    app.run(|handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            let state = handle.state::<BackendState>();
            if let Ok(mut child) = state.child.lock() {
                if let Some(process) = child.take() {
                    let _ = process.kill();
                }
            }
        }
    });
}
