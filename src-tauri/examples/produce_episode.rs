//! Phase P manual verification tool: drives one real, full content.run
//! through the exact same SidecarBridge::call() path the real desktop app
//! uses (real spawned+PyInstaller-packaged sidecar binary, real Rust
//! authority tools answering its nested authority.invoke calls -- real
//! Reddit RSS, real routed model completions, real edge-tts, real Pexels).
//! A GUI click can't be automated from here, but this exercises everything
//! downstream of that click faithfully; the click-to-RPC wiring itself is
//! already covered by the pytest RPC-subprocess suite and the browser-based
//! mock-IPC verification done for the U6 redesign.
//!
//! Usage (from the project root, so `.env` and `config/` resolve):
//!   cargo run --manifest-path src-tauri/Cargo.toml --example produce_episode

use kronara_authority::sidecar_bridge::SidecarBridge;
use serde_json::json;
use std::path::PathBuf;
use std::time::Instant;

fn main() {
    let data_dir = PathBuf::from(".kronara").join("runtime");
    let bridge = SidecarBridge::new(data_dir).expect("failed to configure the sidecar bridge");

    let story_id = format!("owned_manual_verify_{}", std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs());

    println!("Requesting content.run (story_id={story_id})...");
    let started = Instant::now();
    let result = bridge.call(
        "content.run",
        json!({
            "story_id": story_id,
            "subreddits": ["nosleep"],
            "sort": "hot",
            "limit": 25,
            "target_duration_seconds": 90,
            "program_id": "viernes-paranormal",
        }),
    );
    let elapsed = started.elapsed();

    match result {
        Ok(value) => {
            println!("\ncontent.run completed in {:.1}s\n", elapsed.as_secs_f64());
            println!("{}", serde_json::to_string_pretty(&value).unwrap());
        }
        Err(error) => {
            println!("\ncontent.run FAILED after {:.1}s: {error}", elapsed.as_secs_f64());
            std::process::exit(1);
        }
    }
}
