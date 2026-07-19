use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::fmt;

const OPENROUTER_URL: &str = "https://openrouter.ai/api/v1/chat/completions";
const GROQ_URL: &str = "https://api.groq.com/openai/v1/chat/completions";
const ALLOWED_MODELS: &[&str] = &[
    "qwen/qwen3-235b-a22b",
    "moonshotai/kimi-k2",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "tencent/hy3:free",
];

#[derive(Clone)]
pub struct ModelProvider {
    provider: String,
    api_key: String,
    endpoint: String,
    configured_model: Option<String>,
}

impl fmt::Debug for ModelProvider {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("ModelProvider")
            .field("provider", &self.provider)
            .field("api_key", &"[REDACTED]")
            .field("endpoint", &self.endpoint)
            .field("configured_model", &self.configured_model)
            .finish()
    }
}

impl ModelProvider {
    pub fn openrouter(api_key: &str) -> Result<Self, String> {
        Self::custom("openrouter", api_key, "https://openrouter.ai/api/v1")
    }

    pub fn groq(api_key: &str, configured_model: &str) -> Result<Self, String> {
        let mut provider = Self::custom("groq", api_key, "https://api.groq.com/openai/v1")?;
        if configured_model.trim().is_empty() {
            return Err("Groq requires a configured catalog model".into());
        }
        provider.configured_model = Some(configured_model.trim().to_owned());
        Ok(provider)
    }

    pub fn custom(provider: &str, api_key: &str, base_url: &str) -> Result<Self, String> {
        if api_key.trim().is_empty() {
            return Err("model provider credential is missing".into());
        }
        let normalized = base_url.trim_end_matches('/');
        let expected = match provider {
            "openrouter" => "https://openrouter.ai/api/v1",
            "groq" => "https://api.groq.com/openai/v1",
            _ => return Err("model provider is not allowlisted".into()),
        };
        if normalized != expected {
            return Err("model provider host is not pinned".into());
        }
        Ok(Self {
            provider: provider.to_owned(),
            api_key: api_key.trim().to_owned(),
            endpoint: format!("{normalized}/chat/completions"),
            configured_model: None,
        })
    }

    fn resolve_model(&self, requested: &str) -> Option<String> {
        if requested == "groq-live-catalog" && self.provider == "groq" {
            return self.configured_model.clone();
        }
        Some(requested.to_owned())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelCandidateRequest {
    pub provider: String,
    pub model_id: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ModelCompletionRequest {
    pub task: String,
    pub candidates: Vec<ModelCandidateRequest>,
    pub system: String,
    pub input: Value,
    pub response_schema: Value,
    pub max_tokens: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ModelCompletionReceipt {
    pub payload: Value,
    pub provider: String,
    pub model: String,
    pub fallback_used: bool,
    pub usage: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ModelHttpResponse {
    pub status: u16,
    pub json: Value,
}

pub trait ModelHttpClient: Send {
    fn post(
        &self,
        url: &str,
        headers: BTreeMap<String, String>,
        body: Value,
    ) -> Result<ModelHttpResponse, String>;
}

pub struct ReqwestModelHttpClient {
    client: reqwest::blocking::Client,
}

impl ReqwestModelHttpClient {
    pub fn new() -> Result<Self, String> {
        Ok(Self {
            client: reqwest::blocking::Client::builder()
                .https_only(true)
                .timeout(std::time::Duration::from_secs(90))
                .build()
                .map_err(|_| "model HTTP client is unavailable")?,
        })
    }
}

impl ModelHttpClient for ReqwestModelHttpClient {
    fn post(
        &self,
        url: &str,
        headers: BTreeMap<String, String>,
        body: Value,
    ) -> Result<ModelHttpResponse, String> {
        if url != OPENROUTER_URL && url != GROQ_URL {
            return Err("model request host is not pinned".into());
        }
        let mut request = self.client.post(url).json(&body);
        for (key, value) in headers {
            request = request.header(&key, value);
        }
        let response = request
            .send()
            .map_err(|_| "model provider is unavailable".to_string())?;
        let status = response.status().as_u16();
        let json = response
            .json::<Value>()
            .map_err(|_| "model provider returned invalid JSON".to_string())?;
        Ok(ModelHttpResponse { status, json })
    }
}

pub struct ModelGateway<C: ModelHttpClient> {
    providers: Vec<ModelProvider>,
    http: C,
}

impl<C: ModelHttpClient> ModelGateway<C> {
    pub fn new(providers: Vec<ModelProvider>, http: C) -> Self {
        Self { providers, http }
    }

    pub fn http(&self) -> &C {
        &self.http
    }

    pub fn complete(
        &self,
        request: ModelCompletionRequest,
    ) -> Result<ModelCompletionReceipt, String> {
        self.validate(&request)?;
        let mut last_error = "no configured provider for model route".to_string();
        for (index, candidate) in request.candidates.iter().enumerate() {
            let Some(provider) = self
                .providers
                .iter()
                .find(|item| item.provider == candidate.provider)
            else {
                last_error = format!("provider unavailable: {}", candidate.provider);
                continue;
            };
            let Some(model) = provider.resolve_model(&candidate.model_id) else {
                last_error = "dynamic model catalog is unavailable".into();
                continue;
            };
            let response_format = if candidate.model_id == "tencent/hy3:free"
                || request.response_schema.get("properties").is_none()
            {
                json!({"type": "json_object"})
            } else {
                json!({
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name(&request.task),
                        "strict": true,
                        "schema": request.response_schema,
                    }
                })
            };
            let body = json!({
                "model": model,
                "messages": [
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": serde_json::to_string(&request.input).unwrap_or_default()}
                ],
                "response_format": response_format,
                "max_tokens": request.max_tokens,
                "temperature": 0.7,
                "stream": false,
            });
            let headers = BTreeMap::from([
                (
                    "Authorization".to_string(),
                    format!("Bearer {}", provider.api_key),
                ),
                ("Content-Type".to_string(), "application/json".to_string()),
                ("X-OpenRouter-Title".to_string(), "Kronara".to_string()),
            ]);
            let response = match self.http.post(&provider.endpoint, headers, body) {
                Ok(value) => value,
                Err(error) => {
                    last_error = error;
                    continue;
                }
            };
            if !(200..300).contains(&response.status) {
                last_error = format!("model provider failed with status {}", response.status);
                continue;
            }
            let Some(content) = response.json.pointer("/choices/0/message/content").cloned() else {
                last_error = "model response content is missing".into();
                continue;
            };
            let payload = match content {
                Value::Object(_) => content,
                Value::String(text) => match serde_json::from_str::<Value>(&text) {
                    Ok(value) => value,
                    Err(_) => {
                        last_error = "model returned invalid structured content".into();
                        continue;
                    }
                },
                _ => {
                    last_error = "model returned unsupported content".into();
                    continue;
                }
            };
            if !payload_matches_schema(&payload, &request.response_schema) {
                last_error = "model structured payload failed schema validation".into();
                continue;
            }
            return Ok(ModelCompletionReceipt {
                payload,
                provider: provider.provider.clone(),
                model: candidate.model_id.clone(),
                fallback_used: index > 0,
                usage: response
                    .json
                    .get("usage")
                    .cloned()
                    .unwrap_or_else(|| json!({})),
            });
        }
        Err(last_error)
    }

    fn validate(&self, request: &ModelCompletionRequest) -> Result<(), String> {
        if request.task.is_empty()
            || request.system.trim().is_empty()
            || request.system.len() > 20_000
            || !request.input.is_object()
            || !request.response_schema.is_object()
            || request.candidates.is_empty()
            || request.candidates.len() > 5
            || !(1..=8192).contains(&request.max_tokens)
        {
            return Err("invalid bounded model request".into());
        }
        for candidate in &request.candidates {
            let allowed = ALLOWED_MODELS.contains(&candidate.model_id.as_str())
                || (candidate.provider == "groq" && candidate.model_id == "groq-live-catalog");
            if !allowed {
                return Err(format!("model is not allowlisted: {}", candidate.model_id));
            }
        }
        Ok(())
    }
}

fn payload_matches_schema(payload: &Value, schema: &Value) -> bool {
    let Some(object) = payload.as_object() else {
        return false;
    };
    schema
        .get("required")
        .and_then(Value::as_array)
        .is_none_or(|required| {
            required
                .iter()
                .filter_map(Value::as_str)
                .all(|field| object.contains_key(field))
        })
}

fn schema_name(task: &str) -> String {
    let safe = task
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() {
                character
            } else {
                '_'
            }
        })
        .collect::<String>();
    format!("kronara_{safe}")
}
