#[tauri::command]
fn backend_url() -> Option<String> {
    std::env::var("AGENTHEIM_CODE_BACKEND_URL").ok()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(|app| {
            let _ = app.handle();
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Agentheim Code");
}

fn main() {
    run();
}

#[cfg(test)]
mod tests {
    #[test]
    fn it_compiles() {
        assert_eq!(2 + 2, 4);
    }
}
