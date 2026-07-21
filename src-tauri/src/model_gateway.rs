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
    // Groq-hosted, verified current as of 2026-07 (console.groq.com/docs/models):
    // llama-3.3-70b-versatile and openai/gpt-oss-120b are production tier;
    // qwen/qwen3.6-27b is preview but the highest-intelligence model Groq
    // hosts. Each has its own independent per-model rate-limit bucket, so
    // listing several multiplies real throughput, not just redundancy.
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "qwen/qwen3.6-27b",
];

#[derive(Clone)]
pub struct ModelProvider {
    provider: String,
    api_key: String,
    endpoint: String,
}

impl fmt::Debug for ModelProvider {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("ModelProvider")
            .field("provider", &self.provider)
            .field("api_key", &"[REDACTED]")
            .field("endpoint", &self.endpoint)
            .finish()
    }
}

impl ModelProvider {
    pub fn openrouter(api_key: &str) -> Result<Self, String> {
        Self::custom("openrouter", api_key, "https://openrouter.ai/api/v1")
    }

    pub fn groq(api_key: &str) -> Result<Self, String> {
        Self::custom("groq", api_key, "https://api.groq.com/openai/v1")
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
        })
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
        let mut attempt_index = 0u32;
        for candidate in request.candidates.iter() {
            let matching_providers: Vec<&ModelProvider> = self
                .providers
                .iter()
                .filter(|item| item.provider == candidate.provider)
                .collect();
            if matching_providers.is_empty() {
                last_error = format!("provider unavailable: {}", candidate.provider);
                continue;
            }
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
            let mut body = json!({
                "model": candidate.model_id,
                "messages": [
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": serde_json::to_string(&request.input).unwrap_or_default()}
                ],
                "response_format": response_format,
                "max_tokens": request.max_tokens,
                "temperature": 0.7,
                "stream": false,
            });
            if candidate.provider == "openrouter" {
                // Found via a real run: a free reasoning-hybrid candidate
                // (nvidia/nemotron :free) spent its entire max_tokens budget
                // narrating visible chain-of-thought ("We need to produce a
                // JSON object... Let's count words...") and never reached
                // the actual answer, so every fallback attempt died with
                // "model returned invalid structured content". OpenRouter's
                // unified `reasoning.enabled=false` asks any reasoning-
                // capable candidate to skip that internal narration; models
                // without a reasoning mode (qwen, kimi, hy3) ignore it.
                // OpenRouter-specific: Groq's own API rejects an unrecognized
                // `reasoning` property outright (400 "property 'reasoning' is
                // unsupported"), so this must not be sent there.
                body["reasoning"] = json!({"enabled": false});
            }
            // Cascade across every configured key for this provider (e.g. a
            // second or third OpenRouter/Groq account, added specifically so
            // an exhausted key doesn't stall the whole model) before giving
            // up on this model and moving to the next candidate.
            for provider in &matching_providers {
                attempt_index += 1;
                let headers = BTreeMap::from([
                    (
                        "Authorization".to_string(),
                        format!("Bearer {}", provider.api_key),
                    ),
                    ("Content-Type".to_string(), "application/json".to_string()),
                    ("X-OpenRouter-Title".to_string(), "Kronara".to_string()),
                ]);
                let response = match self.http.post(&provider.endpoint, headers, body.clone()) {
                    Ok(value) => value,
                    Err(error) => {
                        // Distinct from the non-2xx branch below: this is the
                        // request never getting a response at all (timeout,
                        // connection refused, DNS, TLS) -- previously silent,
                        // so a candidate could vanish from the fallback chain
                        // with zero trace of why.
                        eprintln!(
                            "[model_gateway] request failed before a response arrived model={} error={error}",
                            candidate.model_id
                        );
                        last_error = error;
                        continue;
                    }
                };
                if !(200..300).contains(&response.status) {
                    // The RPC caller only ever sees `last_error`'s short, generic
                    // form (never leak provider internals over the wire) -- but a
                    // real failure (rate limit, expired free-tier model, an
                    // exhausted credit balance) was previously invisible to
                    // anyone, including whoever runs Kronara locally. This lands
                    // in the same place Python's stderr does when run via a
                    // console (`cargo run`/`cargo run --example`); a real
                    // shipped GUI build has no attached console for this to
                    // reach yet -- a follow-up, not solved here.
                    eprintln!(
                        "[model_gateway] non-2xx status={} model={} body={}",
                        response.status, candidate.model_id, response.json
                    );
                    last_error = format!("model provider failed with status {}", response.status);
                    continue;
                }
                let Some(content) = response.json.pointer("/choices/0/message/content").cloned()
                else {
                    eprintln!(
                        "[model_gateway] missing content model={} body={}",
                        candidate.model_id, response.json
                    );
                    last_error = "model response content is missing".into();
                    continue;
                };
                let payload = match content {
                    Value::Object(_) => content,
                    Value::String(text) => match serde_json::from_str::<Value>(&text) {
                        Ok(value) => value,
                        Err(error) => {
                            // Local stderr log only (see SidecarProcess::spawn) --
                            // seeing the actual text is the only way to tell
                            // "truncated by max_tokens" from "wrapped in a
                            // markdown fence" from something else entirely,
                            // instead of guessing at the fix.
                            eprintln!(
                                "[model_gateway] non-JSON string content model={} error={error} text={text:?}",
                                candidate.model_id
                            );
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
                    eprintln!(
                        "[model_gateway] schema mismatch model={} payload={payload}",
                        candidate.model_id
                    );
                    last_error = "model structured payload failed schema validation".into();
                    continue;
                }
                return Ok(ModelCompletionReceipt {
                    payload,
                    provider: provider.provider.clone(),
                    model: candidate.model_id.clone(),
                    fallback_used: attempt_index > 1,
                    usage: response
                        .json
                        .get("usage")
                        .cloned()
                        .unwrap_or_else(|| json!({})),
                });
            }
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
            if !ALLOWED_MODELS.contains(&candidate.model_id.as_str()) {
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
