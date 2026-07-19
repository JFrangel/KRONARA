use serde_json::{json, Value};
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;
use uuid::Uuid;

const ALLOWED_METHODS: &[&str] = &[
    "operations.chat",
    "operations.context",
    "tools.timeline",
    "memory.search",
    "rag.retrieve_v3",
    "story.test",
    "run.cancel",
    "run.progress",
    "agent.capabilities",
];

pub struct SidecarBridge {
    process: Mutex<Option<SidecarProcess>>,
    token: String,
    data_dir: PathBuf,
}

struct SidecarProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl SidecarBridge {
    pub fn new(data_dir: PathBuf) -> Self {
        Self {
            process: Mutex::new(None),
            token: Uuid::new_v4().simple().to_string(),
            data_dir,
        }
    }

    pub fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        if !is_allowed_method(method) {
            return Err("RPC method is not authorized by Rust".into());
        }
        self.call_inner(method, params)
    }

    pub fn sync_control(&self, paused: bool) -> Result<(), String> {
        self.call_inner("operations.control_snapshot", json!({"paused": paused}))?;
        Ok(())
    }

    fn call_inner(&self, method: &str, params: Value) -> Result<Value, String> {
        if !params.is_object() {
            return Err("RPC params must be an object".into());
        }
        let mut guard = self
            .process
            .lock()
            .map_err(|_| "sidecar bridge is unavailable".to_string())?;
        if guard.is_none() {
            *guard = Some(SidecarProcess::spawn(&self.token, &self.data_dir)?);
        }
        let result = guard
            .as_mut()
            .expect("sidecar process initialized")
            .request(method, params);
        if result.is_err() {
            guard.take();
        }
        result
    }
}

impl SidecarProcess {
    fn spawn(token: &str, data_dir: &Path) -> Result<Self, String> {
        fs::create_dir_all(data_dir).map_err(|_| "cannot create local runtime directory")?;
        let binary = locate_sidecar()?;
        let mut command = Command::new(binary);
        command.env_clear();
        for key in [
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "PATH",
            "USERPROFILE",
            "LOCALAPPDATA",
        ] {
            if let Some(value) = std::env::var_os(key) {
                command.env(key, value);
            }
        }
        command
            .arg("--data-dir")
            .arg(data_dir)
            .env("KRONARA_RPC_SESSION_TOKEN", token)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command
            .spawn()
            .map_err(|_| "cannot start the cognitive sidecar".to_string())?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "sidecar input is unavailable".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "sidecar output is unavailable".to_string())?;
        let mut process = Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 1,
        };
        let handshake =
            process.request("handshake", json!({"token": token, "protocol_version": 1}))?;
        if handshake.get("protocol_version") != Some(&json!(1)) {
            return Err("sidecar protocol handshake failed".into());
        }
        Ok(process)
    }

    fn request(&mut self, method: &str, params: Value) -> Result<Value, String> {
        let request_id = self.next_id;
        self.next_id += 1;
        let request = json!({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        });
        serde_json::to_writer(&mut self.stdin, &request)
            .map_err(|_| "cannot encode RPC request".to_string())?;
        self.stdin
            .write_all(b"\n")
            .and_then(|_| self.stdin.flush())
            .map_err(|_| "cannot send RPC request".to_string())?;
        let mut line = String::new();
        if self
            .stdout
            .read_line(&mut line)
            .map_err(|_| "cannot read RPC response".to_string())?
            == 0
        {
            return Err("cognitive sidecar closed unexpectedly".into());
        }
        let response: Value =
            serde_json::from_str(&line).map_err(|_| "invalid RPC response".to_string())?;
        if response.get("id") != Some(&json!(request_id)) {
            return Err("RPC response identity mismatch".into());
        }
        if let Some(error) = response.get("error") {
            let code = error.get("code").and_then(Value::as_i64).unwrap_or(-32603);
            let message = error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("RPC request failed");
            return Err(format!("RPC {code}: {message}"));
        }
        response
            .get("result")
            .cloned()
            .ok_or_else(|| "RPC response has no result".to_string())
    }
}

impl Drop for SidecarProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub fn is_allowed_method(method: &str) -> bool {
    ALLOWED_METHODS.contains(&method)
}

pub fn is_effectful_method(method: &str) -> bool {
    matches!(method, "story.test")
}

fn locate_sidecar() -> Result<PathBuf, String> {
    let mut candidates = Vec::new();
    if let Ok(executable) = std::env::current_exe() {
        if let Some(parent) = executable.parent() {
            candidates.push(parent.join("kronara-sidecar.exe"));
            candidates.push(parent.join("kronara-sidecar-x86_64-pc-windows-msvc.exe"));
        }
    }
    candidates.push(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("binaries")
            .join("kronara-sidecar-x86_64-pc-windows-msvc.exe"),
    );
    candidates
        .into_iter()
        .find(|candidate| candidate.is_file())
        .ok_or_else(|| "packaged cognitive sidecar was not found".to_string())
}

#[cfg(test)]
mod tests {
    use super::{is_allowed_method, is_effectful_method};

    #[test]
    fn bridge_exposes_only_bounded_cognitive_methods() {
        assert!(is_allowed_method("operations.chat"));
        assert!(is_allowed_method("story.test"));
        assert!(!is_allowed_method("shell.execute"));
        assert!(!is_allowed_method("publication.publish"));
    }

    #[test]
    fn global_pause_can_distinguish_local_actions_from_observation() {
        assert!(is_effectful_method("story.test"));
        assert!(!is_effectful_method("operations.chat"));
        assert!(!is_effectful_method("run.cancel"));
    }
}
