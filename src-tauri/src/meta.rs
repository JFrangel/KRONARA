use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;
use std::time::{SystemTime, UNIX_EPOCH};

const METRICS: &[(&str, &str)] = &[
    ("plays", "post_video_views"),
    ("completions", "post_video_complete_views_organic"),
    ("average_watch_time_ms", "post_video_avg_time_watched"),
    ("reach", "post_impressions_unique"),
    ("shares", "post_video_social_actions"),
];

#[derive(Clone)]
pub struct MetaProvider {
    page_access_token: String,
    graph_version: String,
}

impl fmt::Debug for MetaProvider {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("MetaProvider")
            .field("page_access_token", &"[REDACTED]")
            .field("graph_version", &self.graph_version)
            .finish()
    }
}

impl MetaProvider {
    pub fn new(page_access_token: &str, graph_version: &str) -> Result<Self, String> {
        let version = graph_version.trim();
        let valid_version = version.starts_with('v')
            && version[1..].split_once('.').is_some_and(|(major, minor)| {
                !major.is_empty()
                    && major.len() <= 3
                    && major.chars().all(|value| value.is_ascii_digit())
                    && minor.len() == 1
                    && minor.chars().all(|value| value.is_ascii_digit())
            });
        if page_access_token.trim().is_empty() || !valid_version {
            return Err("Meta token and explicit Graph API version are required".into());
        }
        Ok(Self {
            page_access_token: page_access_token.trim().to_owned(),
            graph_version: version.to_owned(),
        })
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct MetaHttpResponse {
    pub status: u16,
    pub json: Value,
}

pub trait MetaHttpClient: Send {
    fn get(&self, url: &str, headers: BTreeMap<String, String>)
        -> Result<MetaHttpResponse, String>;
}

pub struct ReqwestMetaHttpClient {
    client: reqwest::blocking::Client,
}

impl ReqwestMetaHttpClient {
    pub fn new() -> Result<Self, String> {
        Ok(Self {
            client: reqwest::blocking::Client::builder()
                .https_only(true)
                .timeout(std::time::Duration::from_secs(30))
                .build()
                .map_err(|_| "Meta HTTP client is unavailable")?,
        })
    }
}

impl MetaHttpClient for ReqwestMetaHttpClient {
    fn get(
        &self,
        url: &str,
        headers: BTreeMap<String, String>,
    ) -> Result<MetaHttpResponse, String> {
        if !url.starts_with("https://graph.facebook.com/v") {
            return Err("Meta request host is not pinned".into());
        }
        let mut request = self.client.get(url);
        for (key, value) in headers {
            request = request.header(&key, value);
        }
        let response = request
            .send()
            .map_err(|_| "Meta metrics are unavailable".to_string())?;
        let status = response.status().as_u16();
        let json = response
            .json::<Value>()
            .map_err(|_| "Meta returned invalid JSON".to_string())?;
        Ok(MetaHttpResponse { status, json })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MetaMetricReceipt {
    pub schema_version: u8,
    pub remote_id: String,
    pub observed_at: u64,
    pub metrics: BTreeMap<String, Value>,
    pub evidence_ref: String,
}

pub struct MetaMetricsGateway<C: MetaHttpClient> {
    provider: MetaProvider,
    http: C,
}

impl<C: MetaHttpClient> MetaMetricsGateway<C> {
    pub fn new(provider: MetaProvider, http: C) -> Self {
        Self { provider, http }
    }

    pub fn provider(&self) -> &MetaProvider {
        &self.provider
    }

    pub fn http(&self) -> &C {
        &self.http
    }

    pub fn read(&self, remote_id: &str) -> Result<MetaMetricReceipt, String> {
        if remote_id.is_empty()
            || remote_id.len() > 128
            || !remote_id
                .chars()
                .all(|value| value.is_ascii_alphanumeric() || value == '_' || value == '-')
        {
            return Err("Meta remote id is invalid".into());
        }
        let remote_metrics = METRICS
            .iter()
            .map(|(_, remote)| *remote)
            .collect::<Vec<_>>()
            .join(",");
        let url = format!(
            "https://graph.facebook.com/{}/{remote_id}/video_insights?metric={remote_metrics}",
            self.provider.graph_version
        );
        let headers = BTreeMap::from([(
            "Authorization".to_string(),
            format!("Bearer {}", self.provider.page_access_token),
        )]);
        let response = self.http.get(&url, headers)?;
        if !(200..300).contains(&response.status) {
            return Err(format!(
                "Meta metrics failed with status {}",
                response.status
            ));
        }
        let rows = response
            .json
            .get("data")
            .and_then(Value::as_array)
            .ok_or_else(|| "Meta metrics data is missing".to_string())?;
        let mut by_remote = BTreeMap::new();
        for row in rows {
            let Some(name) = row.get("name").and_then(Value::as_str) else {
                continue;
            };
            let Some(value) = row
                .get("values")
                .and_then(Value::as_array)
                .and_then(|values| values.first())
                .and_then(|value| value.get("value"))
                .cloned()
            else {
                continue;
            };
            by_remote.insert(name.to_owned(), value);
        }
        let mut metrics = BTreeMap::new();
        for (canonical, remote) in METRICS {
            if let Some(value) = by_remote.get(*remote) {
                let normalized = if *canonical == "shares" {
                    value.get("share").cloned().unwrap_or_else(|| value.clone())
                } else {
                    value.clone()
                };
                metrics.insert((*canonical).to_owned(), normalized);
            }
        }
        let observed_at = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "system clock is invalid".to_string())?
            .as_secs();
        let digest = format!(
            "{:x}",
            Sha256::digest(format!("{remote_id}:{observed_at}:{metrics:?}").as_bytes())
        );
        Ok(MetaMetricReceipt {
            schema_version: 1,
            remote_id: remote_id.to_owned(),
            observed_at,
            metrics,
            evidence_ref: format!("meta://metrics/{remote_id}/{}", &digest[..20]),
        })
    }
}
