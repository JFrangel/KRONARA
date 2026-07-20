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
pub struct RedditConfig {
    pub enabled: bool,
    pub client_id: Option<SecretString>,
    pub client_secret: Option<SecretString>,
    pub user_agent: String,
    pub contract_reference: Option<String>,
}

#[derive(Debug, Clone)]
pub struct MetaConfig {
    pub enabled: bool,
    pub page_id: Option<String>,
    pub page_token: Option<SecretString>,
    pub graph_version: Option<String>,
}

#[derive(Debug, Clone)]
pub struct PexelsConfig {
    pub enabled: bool,
    pub api_key: Option<SecretString>,
    pub contract_reference: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RedditState {
    Ready,
    DisabledByPolicy,
    DisabledMissingCredential,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MetaState {
    Ready,
    DisabledByPolicy,
    DisabledMissingCredential,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PexelsState {
    Ready,
    DisabledByPolicy,
    DisabledMissingCredential,
}

#[derive(Debug, Clone)]
pub struct AppConfig {
    pub environment: String,
    pub data_dir: PathBuf,
    pub max_daily_cost_usd: f64,
    pub max_research_cost_usd: f64,
    pub providers: Vec<ProviderConfig>,
    pub reddit: RedditConfig,
    pub meta: MetaConfig,
    pub pexels: PexelsConfig,
    pub embedding_alias: String,
    pub reranker_alias: Option<String>,
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
        write!(
            formatter,
            "invalid configuration for {}: {}",
            self.variable, self.message
        )
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
        let reddit_enabled = parse_bool(values, "KRONARA_REDDIT_ENABLED", false)?;
        let reddit = RedditConfig {
            enabled: reddit_enabled,
            client_id: non_empty(values, "KRONARA_REDDIT_CLIENT_ID").map(SecretString),
            client_secret: non_empty(values, "KRONARA_REDDIT_CLIENT_SECRET").map(SecretString),
            user_agent: value_or(
                values,
                "KRONARA_REDDIT_USER_AGENT",
                "windows:kronara:v0.4 (contact: configure-me)",
            ),
            contract_reference: non_empty(values, "KRONARA_REDDIT_CONTRACT_REFERENCE"),
        };
        if reddit.enabled {
            for (variable, present) in [
                ("KRONARA_REDDIT_CLIENT_ID", reddit.client_id.is_some()),
                (
                    "KRONARA_REDDIT_CLIENT_SECRET",
                    reddit.client_secret.is_some(),
                ),
                (
                    "KRONARA_REDDIT_CONTRACT_REFERENCE",
                    reddit.contract_reference.is_some(),
                ),
            ] {
                if !present {
                    return Err(ConfigError {
                        variable: variable.to_owned(),
                        message: "required when Reddit is enabled".to_owned(),
                    });
                }
            }
        }
        let meta_enabled = parse_bool(values, "KRONARA_META_ENABLED", false)?;
        let meta = MetaConfig {
            enabled: meta_enabled,
            page_id: non_empty(values, "KRONARA_META_PAGE_ID"),
            page_token: non_empty(values, "KRONARA_META_PAGE_TOKEN").map(SecretString),
            graph_version: non_empty(values, "KRONARA_META_GRAPH_VERSION"),
        };
        if meta.enabled {
            for (variable, present) in [
                ("KRONARA_META_PAGE_ID", meta.page_id.is_some()),
                ("KRONARA_META_PAGE_TOKEN", meta.page_token.is_some()),
                ("KRONARA_META_GRAPH_VERSION", meta.graph_version.is_some()),
            ] {
                if !present {
                    return Err(ConfigError {
                        variable: variable.to_owned(),
                        message: "required when Meta is enabled".to_owned(),
                    });
                }
            }
        }
        let pexels_enabled = parse_bool(values, "KRONARA_PEXELS_ENABLED", false)?;
        let pexels = PexelsConfig {
            enabled: pexels_enabled,
            api_key: non_empty(values, "KRONARA_PEXELS_API_KEY").map(SecretString),
            contract_reference: non_empty(values, "KRONARA_PEXELS_CONTRACT_REFERENCE"),
        };
        if pexels.enabled {
            for (variable, present) in [
                ("KRONARA_PEXELS_API_KEY", pexels.api_key.is_some()),
                (
                    "KRONARA_PEXELS_CONTRACT_REFERENCE",
                    pexels.contract_reference.is_some(),
                ),
            ] {
                if !present {
                    return Err(ConfigError {
                        variable: variable.to_owned(),
                        message: "required when Pexels is enabled".to_owned(),
                    });
                }
            }
        }
        let embedding_alias = value_or(values, "KRONARA_EMBEDDING_ALIAS", "bge_m3");
        if !matches!(
            embedding_alias.as_str(),
            "bge_m3" | "multilingual_e5_large" | "deterministic_dev"
        ) {
            return Err(ConfigError {
                variable: "KRONARA_EMBEDDING_ALIAS".into(),
                message: "unknown embedding alias".into(),
            });
        }
        let reranker_alias = non_empty(values, "KRONARA_RERANKER_ALIAS");
        if reranker_alias
            .as_deref()
            .is_some_and(|value| value != "bge_reranker_v2_m3")
        {
            return Err(ConfigError {
                variable: "KRONARA_RERANKER_ALIAS".into(),
                message: "unknown reranker alias".into(),
            });
        }
        Ok(Self {
            environment: value_or(values, "KRONARA_ENV", "development"),
            data_dir: PathBuf::from(value_or(values, "KRONARA_DATA_DIR", ".kronara")),
            max_daily_cost_usd,
            max_research_cost_usd,
            providers,
            reddit,
            meta,
            pexels,
            embedding_alias,
            reranker_alias,
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

    pub fn reddit_status(&self) -> RedditState {
        if !self.reddit.enabled {
            RedditState::DisabledByPolicy
        } else if self.reddit.client_id.is_none()
            || self.reddit.client_secret.is_none()
            || self.reddit.contract_reference.is_none()
        {
            RedditState::DisabledMissingCredential
        } else {
            RedditState::Ready
        }
    }

    pub fn meta_status(&self) -> MetaState {
        if !self.meta.enabled {
            MetaState::DisabledByPolicy
        } else if self.meta.page_id.is_none()
            || self.meta.page_token.is_none()
            || self.meta.graph_version.is_none()
        {
            MetaState::DisabledMissingCredential
        } else {
            MetaState::Ready
        }
    }

    pub fn pexels_status(&self) -> PexelsState {
        if !self.pexels.enabled {
            PexelsState::DisabledByPolicy
        } else if self.pexels.api_key.is_none() || self.pexels.contract_reference.is_none() {
            PexelsState::DisabledMissingCredential
        } else {
            PexelsState::Ready
        }
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
    values
        .get(key)
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
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

fn parse_bool(
    values: &BTreeMap<String, String>,
    key: &str,
    default: bool,
) -> Result<bool, ConfigError> {
    let Some(raw) = non_empty(values, key) else {
        return Ok(default);
    };
    match raw.to_ascii_lowercase().as_str() {
        "true" | "1" | "yes" => Ok(true),
        "false" | "0" | "no" => Ok(false),
        _ => Err(ConfigError {
            variable: key.to_owned(),
            message: "expected a boolean".to_owned(),
        }),
    }
}
