use serde::{Deserialize, Serialize};

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

pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("failed to run Kronara OS");
}
