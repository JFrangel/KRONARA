use serde_json::{json, Value};
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;
use uuid::Uuid;

use crate::authority_tools::ProductionAuthorityTools;
use crate::config::AppConfig;

const ALLOWED_METHODS: &[&str] = &[
    "operations.chat",
    "operations.context",
    "tools.timeline",
    "memory.search",
    "rag.retrieve_v3",
    "story.test",
    "content.run",
    "performance.learn",
    "run.cancel",
    "run.progress",
    "agent.capabilities",
    "programs.list",
    "episodes.list",
    "schedule.tick",
];

const ALLOWED_AUTHORITY_TOOLS: &[&str] = &[
    "model.health",
    "model.complete",
    "reddit.list_signals",
    "meta.metrics.read",
    "pexels.search_videos",
    "voice.synthesize",
    "publication.publish",
];

pub trait AuthorityToolExecutor: Send {
    fn invoke(&mut self, tool_id: &str, arguments: Value) -> Result<Value, String>;
}

pub fn dispatch_authority_request(
    request: &Value,
    executor: &mut dyn AuthorityToolExecutor,
) -> Option<Value> {
    if request.get("method").and_then(Value::as_str) != Some("authority.invoke") {
        return None;
    }
    let request_id = request.get("id").cloned().unwrap_or(Value::Null);
    let params = request.get("params").and_then(Value::as_object);
    let tool_id = params
        .and_then(|value| value.get("tool_id"))
        .and_then(Value::as_str);
    let arguments = params
        .and_then(|value| value.get("arguments"))
        .filter(|value| value.is_object())
        .cloned();
    let Some(tool_id) = tool_id else {
        return Some(json!({
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32602, "message": "authority tool id is required"}
        }));
    };
    if !ALLOWED_AUTHORITY_TOOLS.contains(&tool_id) {
        return Some(json!({
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32601, "message": "authority tool is not allowed"}
        }));
    }
    let Some(arguments) = arguments else {
        return Some(json!({
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32602, "message": "authority arguments must be an object"}
        }));
    };
    Some(match executor.invoke(tool_id, arguments) {
        Ok(result) => json!({"jsonrpc": "2.0", "id": request_id, "result": result}),
        Err(message) => json!({
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -32020, "message": message}
        }),
    })
}

pub struct SidecarBridge {
    process: Mutex<Option<SidecarProcess>>,
    authority: Mutex<Box<dyn AuthorityToolExecutor>>,
    token: String,
    data_dir: PathBuf,
    embedding_alias: String,
    reranker_alias: Option<String>,
}

struct SidecarProcess {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl SidecarBridge {
    pub fn new(data_dir: PathBuf) -> Result<Self, String> {
        let config = AppConfig::from_env().map_err(|error| error.to_string())?;
        let authority = ProductionAuthorityTools::from_config(&config)?;
        Ok(Self::with_runtime_config(
            data_dir,
            Box::new(authority),
            config.embedding_alias,
            config.reranker_alias,
        ))
    }

    pub fn with_executor(data_dir: PathBuf, authority: Box<dyn AuthorityToolExecutor>) -> Self {
        Self::with_runtime_config(
            data_dir,
            authority,
            "bge_m3".into(),
            Some("bge_reranker_v2_m3".into()),
        )
    }

    pub fn with_runtime_config(
        data_dir: PathBuf,
        authority: Box<dyn AuthorityToolExecutor>,
        embedding_alias: String,
        reranker_alias: Option<String>,
    ) -> Self {
        Self {
            process: Mutex::new(None),
            authority: Mutex::new(authority),
            token: Uuid::new_v4().simple().to_string(),
            data_dir,
            embedding_alias,
            reranker_alias,
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
        let mut authority = self
            .authority
            .lock()
            .map_err(|_| "authority tools are unavailable".to_string())?;
        if guard.is_none() {
            *guard = Some(SidecarProcess::spawn(
                &self.token,
                &self.data_dir,
                &self.embedding_alias,
                self.reranker_alias.as_deref(),
                authority.as_mut(),
            )?);
        }
        let result = guard
            .as_mut()
            .expect("sidecar process initialized")
            .request(method, params, authority.as_mut());
        if result.is_err() {
            guard.take();
        }
        result
    }
}

impl SidecarProcess {
    fn spawn(
        token: &str,
        data_dir: &Path,
        embedding_alias: &str,
        reranker_alias: Option<&str>,
        authority: &mut dyn AuthorityToolExecutor,
    ) -> Result<Self, String> {
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
        // rpc.py deliberately returns a generic "internal error" for any
        // unhandled Python exception (never leak internals over the RPC
        // wire) -- but that means a real crash needs *somewhere* a
        // developer can actually see what happened. A log file survives
        // that; Stdio::null() previously threw the traceback away forever,
        // Stdio::inherit() would dump raw Python tracebacks into a shipped
        // GUI app's own (nonexistent) console. Truncated on every spawn --
        // this is "since the last restart," not a growing history.
        let stderr_log = fs::File::create(data_dir.join("sidecar-stderr.log"))
            .map_err(|_| "cannot create sidecar log file".to_string())?;
        command
            .arg("--data-dir")
            .arg(data_dir)
            .env("KRONARA_RPC_SESSION_TOKEN", token)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::from(stderr_log));
        for argument in sidecar_runtime_args(embedding_alias, reranker_alias) {
            command.arg(argument);
        }
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
        let handshake = process.request(
            "handshake",
            json!({"token": token, "protocol_version": 1}),
            authority,
        )?;
        if handshake.get("protocol_version") != Some(&json!(1)) {
            return Err("sidecar protocol handshake failed".into());
        }
        Ok(process)
    }

    fn request(
        &mut self,
        method: &str,
        params: Value,
        authority: &mut dyn AuthorityToolExecutor,
    ) -> Result<Value, String> {
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
        loop {
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
            if let Some(nested) = dispatch_authority_request(&response, authority) {
                serde_json::to_writer(&mut self.stdin, &nested)
                    .map_err(|_| "cannot encode authority response".to_string())?;
                self.stdin
                    .write_all(b"\n")
                    .and_then(|_| self.stdin.flush())
                    .map_err(|_| "cannot send authority response".to_string())?;
                continue;
            }
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
            return response
                .get("result")
                .cloned()
                .ok_or_else(|| "RPC response has no result".to_string());
        }
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
    matches!(
        method,
        "story.test" | "content.run" | "performance.learn" | "schedule.tick"
    )
}

pub fn sidecar_runtime_args(embedding_alias: &str, reranker_alias: Option<&str>) -> Vec<String> {
    let mut arguments = vec!["--embedding-alias".into(), embedding_alias.into()];
    if let Some(alias) = reranker_alias {
        arguments.push("--reranker-alias".into());
        arguments.push(alias.into());
    }
    arguments
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
        assert!(is_allowed_method("content.run"));
        assert!(is_allowed_method("performance.learn"));
        assert!(is_allowed_method("schedule.tick"));
        assert!(!is_allowed_method("shell.execute"));
        assert!(!is_allowed_method("publication.publish"));
    }

    #[test]
    fn global_pause_can_distinguish_local_actions_from_observation() {
        assert!(is_effectful_method("story.test"));
        assert!(is_effectful_method("content.run"));
        assert!(is_effectful_method("performance.learn"));
        // The autonomous scheduler tick can trigger a real production run
        // (spends model/image budget, writes artifacts) exactly like a
        // user-triggered content.run -- global pause must block it too,
        // not just the interactively-triggered actions.
        assert!(is_effectful_method("schedule.tick"));
        assert!(!is_effectful_method("operations.chat"));
        assert!(!is_effectful_method("run.cancel"));
    }

    #[test]
    fn sidecar_receives_non_secret_embedding_aliases_from_rust_configuration() {
        assert_eq!(
            super::sidecar_runtime_args("bge_m3", Some("bge_reranker_v2_m3")),
            vec![
                "--embedding-alias",
                "bge_m3",
                "--reranker-alias",
                "bge_reranker_v2_m3",
            ]
        );
    }
}
