use kronara_authority::meta::{MetaHttpClient, MetaHttpResponse, MetaMetricsGateway, MetaProvider};
use serde_json::json;
use std::collections::BTreeMap;
use std::sync::Mutex;

struct FakeHttp {
    calls: Mutex<Vec<(String, BTreeMap<String, String>)>>,
}

impl FakeHttp {
    fn new() -> Self {
        Self {
            calls: Mutex::new(Vec::new()),
        }
    }
}

impl MetaHttpClient for FakeHttp {
    fn get(
        &self,
        url: &str,
        headers: BTreeMap<String, String>,
    ) -> Result<MetaHttpResponse, String> {
        self.calls.lock().unwrap().push((url.to_owned(), headers));
        Ok(MetaHttpResponse {
            status: 200,
            json: json!({
                "data": [
                    {"name": "post_video_views", "values": [{"value": 1200}]},
                    {"name": "post_video_complete_views_organic", "values": [{"value": 700}]},
                    {"name": "post_video_avg_time_watched", "values": [{"value": 54000}]},
                    {"name": "post_impressions_unique", "values": [{"value": 1000}]},
                    {"name": "post_video_social_actions", "values": [{"value": {"share": 80}}]}
                ]
            }),
        })
    }
}

#[test]
fn meta_metrics_use_versioned_official_graph_host_and_redact_page_token() {
    let gateway = MetaMetricsGateway::new(
        MetaProvider::new("page-token-secret", "v25.0").unwrap(),
        FakeHttp::new(),
    );

    let receipt = gateway.read("123456789").unwrap();

    assert_eq!(receipt.remote_id, "123456789");
    assert_eq!(receipt.metrics["plays"], json!(1200));
    assert_eq!(receipt.metrics["completions"], json!(700));
    assert_eq!(receipt.metrics["average_watch_time_ms"], json!(54000));
    assert_eq!(receipt.metrics["shares"], json!(80));
    assert!(receipt
        .evidence_ref
        .starts_with("meta://metrics/123456789/"));
    let calls = gateway.http().calls.lock().unwrap();
    assert_eq!(calls.len(), 1);
    assert!(calls[0]
        .0
        .starts_with("https://graph.facebook.com/v25.0/123456789/video_insights?metric="));
    assert_eq!(calls[0].1["Authorization"], "Bearer page-token-secret");
    assert!(!format!("{:?}", gateway.provider()).contains("page-token-secret"));
}

#[test]
fn meta_metrics_fail_closed_for_invalid_version_remote_id_and_missing_metrics() {
    assert!(MetaProvider::new("secret", "latest").is_err());
    let gateway = MetaMetricsGateway::new(
        MetaProvider::new("secret", "v25.0").unwrap(),
        FakeHttp::new(),
    );

    assert!(gateway.read("../../token").is_err());
    assert!(gateway.http().calls.lock().unwrap().is_empty());
}
