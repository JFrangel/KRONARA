use kronara_authority::sidecar_bridge::{dispatch_authority_request, AuthorityToolExecutor};
use kronara_authority::{authority_tools::ProductionAuthorityTools, config::AppConfig};
use serde_json::{json, Value};
use std::collections::BTreeMap;

#[derive(Default)]
struct RecordingExecutor {
    calls: Vec<(String, Value)>,
}

impl AuthorityToolExecutor for RecordingExecutor {
    fn invoke(&mut self, tool_id: &str, arguments: Value) -> Result<Value, String> {
        self.calls.push((tool_id.to_owned(), arguments));
        Ok(json!({"ok": true, "credential_exposed": false}))
    }
}

#[test]
fn nested_authority_request_runs_only_an_allowlisted_rust_tool() {
    let mut executor = RecordingExecutor::default();
    let request = json!({
        "jsonrpc": "2.0",
        "id": "authority-1",
        "method": "authority.invoke",
        "params": {
            "tool_id": "reddit.list_signals",
            "arguments": {"subreddits": ["Historias"]}
        }
    });

    let response = dispatch_authority_request(&request, &mut executor).unwrap();

    assert_eq!(response["id"], "authority-1");
    assert_eq!(response["result"]["ok"], true);
    assert_eq!(executor.calls.len(), 1);
    assert_eq!(executor.calls[0].0, "reddit.list_signals");
}

#[test]
fn nested_authority_request_rejects_shell_and_never_calls_executor() {
    let mut executor = RecordingExecutor::default();
    let request = json!({
        "jsonrpc": "2.0",
        "id": "authority-2",
        "method": "authority.invoke",
        "params": {"tool_id": "shell.execute", "arguments": {"command": "whoami"}}
    });

    let response = dispatch_authority_request(&request, &mut executor).unwrap();

    assert_eq!(response["error"]["code"], -32601);
    assert!(executor.calls.is_empty());
}

#[test]
fn production_authority_reports_model_health_without_exposing_keys_or_using_disabled_networks() {
    let values = BTreeMap::from([
        (
            "KRONARA_OPENROUTER_API_KEY".into(),
            "openrouter-secret".into(),
        ),
        (
            "KRONARA_OPENROUTER_BASE_URL".into(),
            "https://openrouter.ai/api/v1".into(),
        ),
    ]);
    let config = AppConfig::from_values(&values).unwrap();
    let mut tools = ProductionAuthorityTools::from_config(&config).unwrap();

    let health = tools.invoke("model.health", json!({})).unwrap();
    let reddit = tools.invoke("reddit.list_signals", json!({})).unwrap_err();
    let meta = tools
        .invoke("meta.metrics.read", json!({"remote_id": "123"}))
        .unwrap_err();

    assert_eq!(health["models"]["qwen/qwen3-235b-a22b"], "degraded");
    assert_eq!(health["models"]["moonshotai/kimi-k2"], "degraded");
    assert!(reddit.contains("disabled_by_policy"));
    assert!(meta.contains("disabled_by_policy"));
    assert!(!format!("{health:?}{reddit:?}{meta:?}").contains("openrouter-secret"));
}
