use crate::config::{AppConfig, MetaState, PexelsState, ProviderConfig, RedditState};
use crate::meta::{MetaMetricsGateway, MetaProvider, ReqwestMetaHttpClient};
use crate::model_gateway::{
    ModelCompletionRequest, ModelGateway, ModelProvider, ReqwestModelHttpClient,
};
use crate::pexels::{
    DirectPexelsTransport, PexelsAccessPolicy, PexelsAuthority, PexelsCredentials,
    PexelsVideoQuery, ReqwestPexelsHttpClient,
};
use crate::reddit::{
    OAuthRedditTransport, RedditAccessPolicy, RedditAuthority, RedditCredentials,
    RedditSignalQuery, ReqwestRedditHttpClient,
};
use crate::sidecar_bridge::AuthorityToolExecutor;
use serde_json::{json, Value};
use std::collections::BTreeMap;

type LiveReddit = RedditAuthority<OAuthRedditTransport<ReqwestRedditHttpClient>>;
type LiveModels = ModelGateway<ReqwestModelHttpClient>;
type LiveMeta = MetaMetricsGateway<ReqwestMetaHttpClient>;
type LivePexels = PexelsAuthority<DirectPexelsTransport<ReqwestPexelsHttpClient>>;

pub struct ProductionAuthorityTools {
    model: Option<LiveModels>,
    reddit: Option<LiveReddit>,
    meta: Option<LiveMeta>,
    pexels: Option<LivePexels>,
    health: BTreeMap<String, String>,
}

impl ProductionAuthorityTools {
    pub fn from_config(config: &AppConfig) -> Result<Self, String> {
        let mut model_providers = Vec::new();
        // Cascade: every configured key becomes its own ModelProvider entry
        // (see config::provider_variants) -- model_gateway.rs tries each one
        // in turn for a given model before moving to the next candidate
        // model, so a second/third OpenRouter or Groq account picks up
        // automatically when an earlier one runs out of credit or quota.
        let openrouter_entries: Vec<_> = config
            .providers
            .iter()
            .filter(|item| item.provider == "openrouter" && item.api_key.is_some())
            .collect();
        let openrouter_entries = if openrouter_entries.is_empty() {
            config
                .providers
                .iter()
                .filter(|item| {
                    matches!(item.provider.as_str(), "qwen" | "kimi")
                        && item.api_key.is_some()
                        && item.base_url.as_deref().is_some_and(|value| {
                            value.trim_end_matches('/') == "https://openrouter.ai/api/v1"
                        })
                })
                .collect()
        } else {
            openrouter_entries
        };
        for provider in &openrouter_entries {
            model_providers.push(ModelProvider::openrouter(secret(provider)?)?);
        }
        let groq_entries: Vec<_> = config
            .providers
            .iter()
            .filter(|item| item.provider == "groq" && item.api_key.is_some())
            .collect();
        for provider in &groq_entries {
            model_providers.push(ModelProvider::groq(secret(provider)?)?);
        }
        let mut health = BTreeMap::new();
        if !openrouter_entries.is_empty() {
            for model in [
                "qwen/qwen3-235b-a22b",
                "moonshotai/kimi-k2",
                "nvidia/nemotron-3-ultra-550b-a55b:free",
                "nvidia/nemotron-3-super-120b-a12b:free",
                "tencent/hy3:free",
            ] {
                // A configured credential makes the model routable, not proven healthy.
                // Successful structured completion promotes the observed model below.
                health.insert(model.to_owned(), "degraded".to_owned());
            }
        }
        if !groq_entries.is_empty() {
            for model in ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3.6-27b"] {
                health.insert(model.to_owned(), "degraded".to_owned());
            }
        }
        let model = if model_providers.is_empty() {
            None
        } else {
            Some(ModelGateway::new(
                model_providers,
                ReqwestModelHttpClient::new()?,
            ))
        };

        let reddit = if config.reddit_status() == RedditState::Ready {
            let credentials = RedditCredentials::new(
                config
                    .reddit
                    .client_id
                    .as_ref()
                    .map(|value| value.expose())
                    .unwrap_or_default(),
                config
                    .reddit
                    .client_secret
                    .as_ref()
                    .map(|value| value.expose())
                    .unwrap_or_default(),
                &config.reddit.user_agent,
            )
            .map_err(|error| error.to_string())?;
            let policy = RedditAccessPolicy::approved(
                config
                    .reddit
                    .contract_reference
                    .as_deref()
                    .unwrap_or_default(),
            )
            .map_err(|error| error.to_string())?;
            Some(RedditAuthority::new(
                policy,
                OAuthRedditTransport::new(
                    credentials,
                    ReqwestRedditHttpClient::new().map_err(|error| error.to_string())?,
                ),
            ))
        } else {
            None
        };

        let meta = if config.meta_status() == MetaState::Ready {
            let provider = MetaProvider::new(
                config
                    .meta
                    .page_token
                    .as_ref()
                    .map(|value| value.expose())
                    .unwrap_or_default(),
                config.meta.graph_version.as_deref().unwrap_or_default(),
            )?;
            Some(MetaMetricsGateway::new(
                provider,
                ReqwestMetaHttpClient::new()?,
            ))
        } else {
            None
        };

        let pexels = if config.pexels_status() == PexelsState::Ready {
            let credentials = PexelsCredentials::new(
                config
                    .pexels
                    .api_key
                    .as_ref()
                    .map(|value| value.expose())
                    .unwrap_or_default(),
            )
            .map_err(|error| error.to_string())?;
            let policy = PexelsAccessPolicy::approved(
                config
                    .pexels
                    .contract_reference
                    .as_deref()
                    .unwrap_or_default(),
            )
            .map_err(|error| error.to_string())?;
            Some(PexelsAuthority::new(
                policy,
                DirectPexelsTransport::new(
                    credentials,
                    ReqwestPexelsHttpClient::new().map_err(|error| error.to_string())?,
                ),
            ))
        } else {
            None
        };
        Ok(Self {
            model,
            reddit,
            meta,
            pexels,
            health,
        })
    }
}

impl AuthorityToolExecutor for ProductionAuthorityTools {
    fn invoke(&mut self, tool_id: &str, arguments: Value) -> Result<Value, String> {
        match tool_id {
            "model.health" => Ok(json!({"schema_version": 1, "models": self.health})),
            "model.complete" => {
                let request = serde_json::from_value::<ModelCompletionRequest>(arguments)
                    .map_err(|_| "invalid model completion request".to_string())?;
                let receipt = self
                    .model
                    .as_ref()
                    .ok_or_else(|| "models_disabled_missing_credential".to_string())?
                    .complete(request)?;
                self.health
                    .insert(receipt.model.clone(), "healthy".to_owned());
                serde_json::to_value(receipt)
                    .map_err(|_| "model receipt serialization failed".to_string())
            }
            "reddit.list_signals" => {
                let gateway = self
                    .reddit
                    .as_ref()
                    .ok_or_else(|| "reddit_disabled_by_policy".to_string())?;
                let query = serde_json::from_value::<RedditSignalQuery>(arguments)
                    .map_err(|_| "invalid Reddit signal query".to_string())?;
                let page = gateway
                    .list_signals(query)
                    .map_err(|error| format!("reddit_{}", error.code()))?;
                serde_json::to_value(page)
                    .map_err(|_| "Reddit receipt serialization failed".to_string())
            }
            "meta.metrics.read" => {
                let gateway = self
                    .meta
                    .as_ref()
                    .ok_or_else(|| "meta_disabled_by_policy".to_string())?;
                let remote_id = arguments
                    .get("remote_id")
                    .and_then(Value::as_str)
                    .ok_or_else(|| "Meta remote id is required".to_string())?;
                serde_json::to_value(gateway.read(remote_id)?)
                    .map_err(|_| "Meta metric receipt serialization failed".to_string())
            }
            "pexels.search_videos" => {
                let gateway = self
                    .pexels
                    .as_ref()
                    .ok_or_else(|| "pexels_disabled_by_policy".to_string())?;
                let query = serde_json::from_value::<PexelsVideoQuery>(arguments)
                    .map_err(|_| "invalid Pexels video query".to_string())?;
                let page = gateway
                    .search_videos(query)
                    .map_err(|error| format!("pexels_{}", error.code()))?;
                serde_json::to_value(page)
                    .map_err(|_| "Pexels receipt serialization failed".to_string())
            }
            "voice.synthesize" => crate::voice::synthesize(arguments),
            // Publishing is gated on an authorized Meta Page. Until the sandbox
            // Page + token are wired, this reports `not_configured` and posts
            // nothing; the reconciliation/URL helpers are ready for that step.
            "publication.publish" => crate::publishing::publish(None, arguments),
            _ => Err("authority tool is not allowed".into()),
        }
    }
}

fn secret(provider: &ProviderConfig) -> Result<&str, String> {
    provider
        .api_key
        .as_ref()
        .map(|value| value.expose())
        .ok_or_else(|| "model provider credential is unavailable".to_string())
}
