use std::collections::BTreeMap;
use std::env;
use std::fmt;
use std::path::PathBuf;

#[derive(Clone, PartialEq, Eq)]
pub struct SecretString(String);

impl SecretString {
    pub fn expose(&self) -> &str {
        &self.0
    }
}

impl fmt::Debug for SecretString {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("[REDACTED]")
    }
}

#[derive(Debug, Clone)]
pub struct ProviderConfig {
    pub provider: String,
    pub api_key: Option<SecretString>,
    pub model: Option<String>,
    pub base_url: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProviderState {
    Ready,
    DisabledMissingCredential,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProviderStatus {
    pub provider: String,
    pub state: ProviderState,
}

#[derive(Debug, Clone)]
pub struct AppConfig {
    pub environment: String,
    pub data_dir: PathBuf,
    pub max_daily_cost_usd: f64,
    pub max_research_cost_usd: f64,
    pub providers: Vec<ProviderConfig>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConfigError {
    variable: String,
    message: String,
}

impl ConfigError {
    pub fn variable(&self) -> &str {
        &self.variable
    }
}

impl fmt::Display for ConfigError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "invalid configuration for {}: {}", self.variable, self.message)
    }
}

impl std::error::Error for ConfigError {}

impl AppConfig {
    pub fn from_env() -> Result<Self, ConfigError> {
        let _ = dotenvy::dotenv();
        let values = env::vars().collect::<BTreeMap<_, _>>();
        Self::from_values(&values)
    }

    pub fn from_values(values: &BTreeMap<String, String>) -> Result<Self, ConfigError> {
        let max_daily_cost_usd = parse_non_negative(values, "KRONARA_MAX_DAILY_COST_USD", 5.0)?;
        let max_research_cost_usd =
            parse_non_negative(values, "KRONARA_MAX_RESEARCH_COST_USD", 1.0)?;
        let providers = ["QWEN", "KIMI", "OPENROUTER", "GROQ"]
            .into_iter()
            .map(|name| provider(values, name))
            .collect();
        Ok(Self {
            environment: value_or(values, "KRONARA_ENV", "development"),
            data_dir: PathBuf::from(value_or(values, "KRONARA_DATA_DIR", ".kronara")),
            max_daily_cost_usd,
            max_research_cost_usd,
            providers,
        })
    }

    pub fn provider_status(&self) -> Vec<ProviderStatus> {
        self.providers
            .iter()
            .map(|provider| ProviderStatus {
                provider: provider.provider.clone(),
                state: if provider.api_key.is_some() {
                    ProviderState::Ready
                } else {
                    ProviderState::DisabledMissingCredential
                },
            })
            .collect()
    }
}

fn provider(values: &BTreeMap<String, String>, name: &str) -> ProviderConfig {
    let prefix = format!("KRONARA_{name}");
    ProviderConfig {
        provider: name.to_lowercase(),
        api_key: non_empty(values, &format!("{prefix}_API_KEY")).map(SecretString),
        model: non_empty(values, &format!("{prefix}_MODEL")),
        base_url: non_empty(values, &format!("{prefix}_BASE_URL")),
    }
}

fn non_empty(values: &BTreeMap<String, String>, key: &str) -> Option<String> {
    values.get(key).map(|value| value.trim()).filter(|value| !value.is_empty()).map(str::to_owned)
}

fn value_or(values: &BTreeMap<String, String>, key: &str, default: &str) -> String {
    non_empty(values, key).unwrap_or_else(|| default.to_owned())
}

fn parse_non_negative(
    values: &BTreeMap<String, String>,
    key: &str,
    default: f64,
) -> Result<f64, ConfigError> {
    let Some(raw) = non_empty(values, key) else {
        return Ok(default);
    };
    let value = raw.parse::<f64>().map_err(|_| ConfigError {
        variable: key.to_owned(),
        message: "expected a number".to_owned(),
    })?;
    if !value.is_finite() || value < 0.0 {
        return Err(ConfigError {
            variable: key.to_owned(),
            message: "expected a finite non-negative number".to_owned(),
        });
    }
    Ok(value)
}
