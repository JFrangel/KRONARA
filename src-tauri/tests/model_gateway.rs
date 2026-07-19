use kronara_authority::model_gateway::{
    ModelCandidateRequest, ModelCompletionRequest, ModelGateway, ModelHttpClient,
    ModelHttpResponse, ModelProvider,
};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::sync::Mutex;

struct FakeHttp {
    responses: Mutex<Vec<ModelHttpResponse>>,
    calls: Mutex<Vec<(String, BTreeMap<String, String>, Value)>>,
}

impl FakeHttp {
    fn new(responses: Vec<ModelHttpResponse>) -> Self {
        Self {
            responses: Mutex::new(responses.into_iter().rev().collect()),
            calls: Mutex::new(Vec::new()),
        }
    }
}

impl ModelHttpClient for FakeHttp {
    fn post(
        &self,
        url: &str,
        headers: BTreeMap<String, String>,
        body: Value,
    ) -> Result<ModelHttpResponse, String> {
        self.calls
            .lock()
            .unwrap()
            .push((url.to_owned(), headers, body));
        self.responses
            .lock()
            .unwrap()
            .pop()
            .ok_or_else(|| "no response".to_string())
    }
}

fn request(candidates: Vec<ModelCandidateRequest>) -> ModelCompletionRequest {
    ModelCompletionRequest {
        task: "story.concepts".into(),
        candidates,
        system: "Crea historias originales y devuelve JSON.".into(),
        input: json!({"theme": "verdad y lealtad"}),
        response_schema: json!({"type": "object", "required": ["concepts"]}),
        max_tokens: 1024,
    }
}

#[test]
fn model_gateway_falls_back_from_qwen_to_nemotron_on_official_openrouter_host() {
    let http = FakeHttp::new(vec![
        ModelHttpResponse {
            status: 503,
            json: json!({"error": "busy"}),
        },
        ModelHttpResponse {
            status: 200,
            json: json!({
                "choices": [{"message": {"content": "{\"concepts\":[]}"}}],
                "usage": {"total_tokens": 123}
            }),
        },
    ]);
    let gateway = ModelGateway::new(
        vec![ModelProvider::openrouter("super-secret").unwrap()],
        http,
    );

    let receipt = gateway
        .complete(request(vec![
            ModelCandidateRequest {
                provider: "openrouter".into(),
                model_id: "qwen/qwen3-235b-a22b".into(),
            },
            ModelCandidateRequest {
                provider: "openrouter".into(),
                model_id: "nvidia/nemotron-3-super-120b-a12b:free".into(),
            },
        ]))
        .unwrap();

    assert_eq!(receipt.model, "nvidia/nemotron-3-super-120b-a12b:free");
    assert!(receipt.fallback_used);
    assert_eq!(receipt.payload, json!({"concepts": []}));
    assert_eq!(receipt.usage["total_tokens"], 123);
    let calls = gateway.http().calls.lock().unwrap();
    assert_eq!(calls.len(), 2);
    assert!(calls
        .iter()
        .all(|call| call.0 == "https://openrouter.ai/api/v1/chat/completions"));
    assert!(calls
        .iter()
        .all(|call| call.1["Authorization"] == "Bearer super-secret"));
    assert!(!format!("{:?}", receipt).contains("super-secret"));
}

#[test]
fn model_gateway_rejects_unknown_models_and_unpinned_hosts_before_http() {
    assert!(ModelProvider::custom("openrouter", "secret", "https://attacker.example/v1").is_err());
    let gateway = ModelGateway::new(
        vec![ModelProvider::openrouter("secret").unwrap()],
        FakeHttp::new(vec![]),
    );

    let error = gateway
        .complete(request(vec![ModelCandidateRequest {
            provider: "openrouter".into(),
            model_id: "unknown/unapproved-model".into(),
        }]))
        .unwrap_err();

    assert!(error.contains("not allowlisted"));
    assert!(gateway.http().calls.lock().unwrap().is_empty());
}

#[test]
fn model_gateway_falls_back_when_a_provider_returns_invalid_structured_content() {
    let http = FakeHttp::new(vec![
        ModelHttpResponse {
            status: 200,
            json: json!({"choices": [{"message": {"content": "not-json"}}]}),
        },
        ModelHttpResponse {
            status: 200,
            json: json!({"choices": [{"message": {"content": "{\"concepts\":[]}"}}]}),
        },
    ]);
    let gateway = ModelGateway::new(vec![ModelProvider::openrouter("secret").unwrap()], http);

    let receipt = gateway
        .complete(request(vec![
            ModelCandidateRequest {
                provider: "openrouter".into(),
                model_id: "qwen/qwen3-235b-a22b".into(),
            },
            ModelCandidateRequest {
                provider: "openrouter".into(),
                model_id: "nvidia/nemotron-3-super-120b-a12b:free".into(),
            },
        ]))
        .unwrap();

    assert!(receipt.fallback_used);
    assert_eq!(receipt.model, "nvidia/nemotron-3-super-120b-a12b:free");
    assert_eq!(gateway.http().calls.lock().unwrap().len(), 2);
}
