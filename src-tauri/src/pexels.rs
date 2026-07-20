use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PexelsAccessPolicy {
    enabled: bool,
    contract_reference: Option<String>,
}

impl PexelsAccessPolicy {
    pub fn disabled() -> Self {
        Self {
            enabled: false,
            contract_reference: None,
        }
    }

    pub fn approved(contract_reference: &str) -> Result<Self, PexelsError> {
        let reference = contract_reference.trim();
        if reference.is_empty() {
            return Err(PexelsError::new(
                "missing_contract_reference",
                "Pexels approval requires a contract reference",
            ));
        }
        Ok(Self {
            enabled: true,
            contract_reference: Some(reference.to_owned()),
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PexelsOrientation {
    Portrait,
    Landscape,
    Square,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PexelsVideoQuery {
    pub schema_version: u8,
    pub query: String,
    pub orientation: Option<PexelsOrientation>,
    pub per_page: u16,
    pub page: u16,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PexelsRawVideo {
    pub source_id: String,
    pub source_uri: String,
    pub download_url: String,
    pub width: u32,
    pub height: u32,
    pub duration_seconds: u32,
    pub photographer: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PexelsRawPage {
    pub videos: Vec<PexelsRawVideo>,
    pub next_page: Option<u16>,
    pub remaining: Option<f64>,
    pub reset_seconds: Option<u64>,
}

pub trait PexelsTransport {
    fn search(&self, query: &PexelsVideoQuery) -> Result<PexelsRawPage, PexelsError>;
}

#[derive(Clone, PartialEq, Eq)]
pub struct PexelsCredentials {
    api_key: String,
}

impl PexelsCredentials {
    pub fn new(api_key: &str) -> Result<Self, PexelsError> {
        if api_key.trim().is_empty() {
            return Err(PexelsError::new(
                "credentials_invalid",
                "Pexels API key is required",
            ));
        }
        Ok(Self {
            api_key: api_key.trim().to_owned(),
        })
    }

    pub fn api_key(&self) -> &str {
        &self.api_key
    }
}

impl std::fmt::Debug for PexelsCredentials {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("PexelsCredentials")
            .field("api_key", &"[REDACTED]")
            .finish()
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct PexelsHttpResponse {
    pub status: u16,
    pub json: serde_json::Value,
    pub headers: BTreeMap<String, String>,
}

pub trait PexelsHttpClient {
    fn request_search(
        &self,
        credentials: &PexelsCredentials,
        query: &PexelsVideoQuery,
    ) -> Result<PexelsHttpResponse, PexelsError>;
}

pub struct ReqwestPexelsHttpClient {
    client: reqwest::blocking::Client,
}

impl ReqwestPexelsHttpClient {
    const API_ROOT: &'static str = "https://api.pexels.com/videos/search";

    pub fn new() -> Result<Self, PexelsError> {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(20))
            .https_only(true)
            .build()
            .map_err(|_| PexelsError::new("http_client_failed", "HTTP client is unavailable"))?;
        Ok(Self { client })
    }

    pub fn api_root(&self) -> &'static str {
        Self::API_ROOT
    }
}

impl PexelsHttpClient for ReqwestPexelsHttpClient {
    fn request_search(
        &self,
        credentials: &PexelsCredentials,
        query: &PexelsVideoQuery,
    ) -> Result<PexelsHttpResponse, PexelsError> {
        let mut parameters = vec![
            ("query", query.query.clone()),
            ("per_page", query.per_page.to_string()),
            ("page", query.page.to_string()),
        ];
        if let Some(orientation) = &query.orientation {
            let value = match orientation {
                PexelsOrientation::Portrait => "portrait",
                PexelsOrientation::Landscape => "landscape",
                PexelsOrientation::Square => "square",
            };
            parameters.push(("orientation", value.to_owned()));
        }
        let response = self
            .client
            .get(Self::API_ROOT)
            .header("Authorization", credentials.api_key())
            .query(&parameters)
            .send()
            .map_err(|_| PexelsError::new("search_transport_failed", "Pexels API is unavailable"))?;
        let status = response.status().as_u16();
        let headers = response
            .headers()
            .iter()
            .filter_map(|(key, value)| {
                value
                    .to_str()
                    .ok()
                    .map(|text| (key.as_str().to_owned(), text.to_owned()))
            })
            .collect::<BTreeMap<_, _>>();
        let json = response
            .json::<serde_json::Value>()
            .map_err(|_| PexelsError::new("invalid_json", "Pexels returned invalid JSON"))?;
        Ok(PexelsHttpResponse {
            status,
            json,
            headers,
        })
    }
}

pub struct DirectPexelsTransport<C: PexelsHttpClient> {
    credentials: PexelsCredentials,
    http: C,
}

impl<C: PexelsHttpClient> DirectPexelsTransport<C> {
    pub fn new(credentials: PexelsCredentials, http: C) -> Self {
        Self { credentials, http }
    }
}

impl<C: PexelsHttpClient> PexelsTransport for DirectPexelsTransport<C> {
    fn search(&self, query: &PexelsVideoQuery) -> Result<PexelsRawPage, PexelsError> {
        let response = self.http.request_search(&self.credentials, query)?;
        if response.status == 429 {
            let retry = header(&response.headers, "x-ratelimit-reset")
                .and_then(|value| value.parse::<u64>().ok())
                .unwrap_or(60);
            return Err(PexelsError::rate_limited(retry));
        }
        if response.status != 200 {
            return Err(PexelsError::new(
                "search_failed",
                "Pexels search returned a non-success status",
            ));
        }
        let mut page = parse_search_payload(&response.json)?;
        page.remaining = header(&response.headers, "x-ratelimit-remaining")
            .and_then(|value| value.parse::<f64>().ok());
        page.reset_seconds = header(&response.headers, "x-ratelimit-reset")
            .and_then(|value| value.parse::<u64>().ok());
        Ok(page)
    }
}

fn header<'a>(headers: &'a BTreeMap<String, String>, name: &str) -> Option<&'a str> {
    headers
        .iter()
        .find(|(key, _)| key.eq_ignore_ascii_case(name))
        .map(|(_, value)| value.as_str())
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PexelsQueryReceipt {
    pub receipt_id: String,
    pub query_hash: String,
    pub contract_reference: String,
    pub observed_at: u64,
    pub count: usize,
    pub remaining: Option<f64>,
    pub reset_seconds: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PexelsVideoPage {
    pub schema_version: u8,
    pub videos: Vec<PexelsRawVideo>,
    pub next_page: Option<u16>,
    pub receipt: PexelsQueryReceipt,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PexelsError {
    code: String,
    message: String,
    retry_after_seconds: Option<u64>,
}

impl PexelsError {
    pub fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.to_owned(),
            message: message.to_owned(),
            retry_after_seconds: None,
        }
    }

    pub fn rate_limited(retry_after_seconds: u64) -> Self {
        Self {
            code: "rate_limited".into(),
            message: "Pexels rate limit reached".into(),
            retry_after_seconds: Some(retry_after_seconds),
        }
    }

    pub fn code(&self) -> &str {
        &self.code
    }

    pub fn retry_after_seconds(&self) -> Option<u64> {
        self.retry_after_seconds
    }
}

impl std::fmt::Display for PexelsError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for PexelsError {}

pub struct PexelsAuthority<T: PexelsTransport> {
    policy: PexelsAccessPolicy,
    transport: T,
}

impl<T: PexelsTransport> PexelsAuthority<T> {
    pub fn new(policy: PexelsAccessPolicy, transport: T) -> Self {
        Self { policy, transport }
    }

    pub fn search_videos(&self, query: PexelsVideoQuery) -> Result<PexelsVideoPage, PexelsError> {
        if !self.policy.enabled {
            return Err(PexelsError::new(
                "disabled_by_policy",
                "Pexels access is disabled by policy",
            ));
        }
        validate_query(&query)?;
        let raw = self.transport.search(&query)?;
        let query_hash = hash_query(&query)?;
        let observed_at = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| PexelsError::new("clock_error", "system clock is before Unix epoch"))?
            .as_secs();
        let contract_reference = self.policy.contract_reference.clone().ok_or_else(|| {
            PexelsError::new("missing_contract_reference", "approval is incomplete")
        })?;
        let count = raw.videos.len();
        Ok(PexelsVideoPage {
            schema_version: 1,
            videos: raw.videos,
            next_page: raw.next_page,
            receipt: PexelsQueryReceipt {
                receipt_id: format!("pv_{}", &query_hash[..20]),
                query_hash,
                contract_reference,
                observed_at,
                count,
                remaining: raw.remaining,
                reset_seconds: raw.reset_seconds,
            },
        })
    }
}

fn validate_query(query: &PexelsVideoQuery) -> Result<(), PexelsError> {
    if query.schema_version != 1 {
        return Err(PexelsError::new(
            "invalid_schema",
            "unsupported query schema",
        ));
    }
    let trimmed = query.query.trim();
    if trimmed.is_empty() || trimmed.len() > 200 {
        return Err(PexelsError::new(
            "invalid_query_text",
            "search text must be one to two hundred characters",
        ));
    }
    if !(1..=80).contains(&query.per_page) {
        return Err(PexelsError::new(
            "invalid_per_page",
            "per_page must be between one and eighty",
        ));
    }
    if query.page == 0 {
        return Err(PexelsError::new("invalid_page", "page must be at least one"));
    }
    Ok(())
}

fn hash_query(query: &PexelsVideoQuery) -> Result<String, PexelsError> {
    let encoded = serde_json::to_vec(query)
        .map_err(|_| PexelsError::new("query_serialization", "query cannot be serialized"))?;
    Ok(format!("{:x}", Sha256::digest(encoded)))
}

/// Picks one file per video: prefer the "hd" quality mp4 (a sane balance of
/// visual quality vs. download size for a short connective b-roll clip);
/// fall back to the first mp4 file present if no "hd" entry exists.
fn select_video_file(video: &serde_json::Value) -> Option<(&serde_json::Value, String)> {
    let files = video.get("video_files")?.as_array()?;
    let is_mp4 = |file: &&serde_json::Value| {
        file.get("file_type")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|value| value == "video/mp4")
    };
    let hd = files
        .iter()
        .filter(is_mp4)
        .find(|file| file.get("quality").and_then(serde_json::Value::as_str) == Some("hd"));
    let chosen = hd.or_else(|| files.iter().filter(is_mp4).next())?;
    let link = chosen
        .get("link")
        .and_then(serde_json::Value::as_str)?
        .to_owned();
    Some((chosen, link))
}

pub fn parse_search_payload(payload: &serde_json::Value) -> Result<PexelsRawPage, PexelsError> {
    let videos_json = payload
        .get("videos")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| PexelsError::new("invalid_response", "search videos are missing"))?;
    let mut videos = Vec::new();
    for video in videos_json {
        let Some(id) = video.get("id").and_then(serde_json::Value::as_i64) else {
            continue;
        };
        let Some((file, download_url)) = select_video_file(video) else {
            continue; // no usable mp4 file for this result -- skip, don't fail the whole page
        };
        videos.push(PexelsRawVideo {
            source_id: id.to_string(),
            source_uri: video
                .get("url")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            download_url,
            width: file
                .get("width")
                .and_then(serde_json::Value::as_u64)
                .unwrap_or(0) as u32,
            height: file
                .get("height")
                .and_then(serde_json::Value::as_u64)
                .unwrap_or(0) as u32,
            duration_seconds: video
                .get("duration")
                .and_then(serde_json::Value::as_u64)
                .unwrap_or(0) as u32,
            photographer: video
                .get("user")
                .and_then(|user| user.get("name"))
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_owned(),
        });
    }
    let next_page = payload
        .get("next_page")
        .and_then(serde_json::Value::as_str)
        .and_then(|url| {
            url.split("page=")
                .nth(1)
                .and_then(|tail| tail.split('&').next())
                .and_then(|value| value.parse::<u16>().ok())
        });
    Ok(PexelsRawPage {
        videos,
        next_page,
        remaining: None,
        reset_seconds: None,
    })
}
