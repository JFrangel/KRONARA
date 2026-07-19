use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::Mutex;
use tauri::Manager;

pub mod authority_tools;
pub mod config;
pub mod meta;
pub mod model_gateway;
pub mod reddit;
pub mod sidecar_bridge;
pub mod voice;

use sidecar_bridge::{is_effectful_method, SidecarBridge};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Effect {
    WriteArtifact,
    Render,
    Publish,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RiskDecision {
    pub level: String,
    pub codes: Vec<String>,
}

impl RiskDecision {
    pub fn low() -> Self {
        Self {
            level: "low".into(),
            codes: vec![],
        }
    }

    pub fn critical(code: &str) -> Self {
        Self {
            level: "critical".into(),
            codes: vec![code.into()],
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AuthorityError {
    GloballyPaused,
    HumanApprovalRequired,
    Blocked(String),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ActionIntent {
    pub schema_version: u32,
    pub intent_id: String,
    pub kind: String,
    pub arguments: Value,
    pub risk_level: String,
    pub status: String,
    pub idempotency_key: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IntentDecision {
    RequiresApproval,
    Denied(String),
}

pub struct Authority {
    paused: bool,
    mode: String,
}

impl Authority {
    pub fn new(paused: bool, mode: &str) -> Self {
        Self {
            paused,
            mode: mode.into(),
        }
    }

    pub fn authorize(&self, effect: Effect, risk: RiskDecision) -> Result<(), AuthorityError> {
        if self.paused {
            return Err(AuthorityError::GloballyPaused);
        }
        if let Some(code) = risk.codes.iter().find(|code| is_non_overridable(code)) {
            return Err(AuthorityError::Blocked(code.clone()));
        }
        if risk.level == "critical" {
            return Err(AuthorityError::Blocked("critical_risk".into()));
        }
        if self.mode == "manual" || (self.mode == "supervised_auto" && effect == Effect::Publish) {
            return Err(AuthorityError::HumanApprovalRequired);
        }
        Ok(())
    }

    pub fn validate_action_intent(&self, intent: &ActionIntent) -> IntentDecision {
        let valid_identity = intent.schema_version == 1
            && !intent.intent_id.trim().is_empty()
            && !intent.kind.trim().is_empty()
            && !intent.idempotency_key.trim().is_empty();
        let safe_status = intent.status == "requires_approval" || intent.status == "proposed";
        let safe_arguments = !contains_sensitive_key(&intent.arguments);
        if !valid_identity || !safe_status || !safe_arguments {
            return IntentDecision::Denied("invalid_action_intent".into());
        }
        if self.paused {
            return IntentDecision::Denied("globally_paused".into());
        }
        IntentDecision::RequiresApproval
    }
}

fn contains_sensitive_key(value: &Value) -> bool {
    match value {
        Value::Object(values) => values.iter().any(|(key, value)| {
            matches!(
                key.to_ascii_lowercase().as_str(),
                "api_key"
                    | "apikey"
                    | "authorization"
                    | "client_secret"
                    | "password"
                    | "secret"
                    | "token"
            ) || contains_sensitive_key(value)
        }),
        Value::Array(values) => values.iter().any(contains_sensitive_key),
        _ => false,
    }
}

fn is_non_overridable(code: &str) -> bool {
    matches!(
        code,
        "rights_insufficient"
            | "credentials_invalid"
            | "platform_policy_violation"
            | "render_defective"
            | "publication_ambiguous"
            | "budget_exhausted"
    )
}

#[derive(Default)]
pub struct OperationalControl {
    paused: Mutex<bool>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ControlStateSnapshot {
    pub mode: String,
    pub paused: bool,
    pub publication_authority: String,
}

impl OperationalControl {
    fn snapshot(&self) -> Result<ControlStateSnapshot, String> {
        let paused = *self
            .paused
            .lock()
            .map_err(|_| "operational control is unavailable".to_string())?;
        Ok(ControlStateSnapshot {
            mode: "full_auto".into(),
            paused,
            publication_authority: "rust_only".into(),
        })
    }
}

#[tauri::command]
fn operations_rpc(
    bridge: tauri::State<'_, SidecarBridge>,
    control: tauri::State<'_, OperationalControl>,
    method: String,
    params: Value,
) -> Result<Value, String> {
    let snapshot = control.snapshot()?;
    bridge.sync_control(snapshot.paused)?;
    if snapshot.paused && is_effectful_method(&method) {
        return Err("global pause blocks new cognitive actions".into());
    }
    bridge.call(&method, params)
}

#[tauri::command]
fn get_control_state(
    control: tauri::State<'_, OperationalControl>,
) -> Result<ControlStateSnapshot, String> {
    control.snapshot()
}

#[tauri::command]
fn set_global_pause(
    control: tauri::State<'_, OperationalControl>,
    bridge: tauri::State<'_, SidecarBridge>,
    paused: bool,
) -> Result<ControlStateSnapshot, String> {
    *control
        .paused
        .lock()
        .map_err(|_| "operational control is unavailable".to_string())? = paused;
    let snapshot = control.snapshot()?;
    let _ = bridge.sync_control(snapshot.paused);
    Ok(snapshot)
}

pub fn run() {
    tauri::Builder::default()
        .manage(OperationalControl::default())
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?.join("runtime");
            app.manage(SidecarBridge::new(data_dir)?);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            operations_rpc,
            get_control_state,
            set_global_pause
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Kronara OS");
}
