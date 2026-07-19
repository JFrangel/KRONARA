use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RedditAccessPolicy {
    enabled: bool,
    contract_reference: Option<String>,
}

impl RedditAccessPolicy {
    pub fn disabled() -> Self {
        Self {
            enabled: false,
            contract_reference: None,
        }
    }

    pub fn approved(contract_reference: &str) -> Result<Self, RedditError> {
        let reference = contract_reference.trim();
        if reference.is_empty() {
            return Err(RedditError::new(
                "missing_contract_reference",
                "Reddit approval requires a contract reference",
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
pub enum RedditSort {
    New,
    Hot,
    Top,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum RedditTimeFilter {
    Hour,
    Day,
    Week,
    Month,
    Year,
    All,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RedditSignalQuery {
    pub schema_version: u8,
    pub subreddits: Vec<String>,
    pub sort: RedditSort,
    pub time_filter: Option<RedditTimeFilter>,
    pub after: Option<String>,
    pub limit: u16,
    pub include_nsfw: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RedditRawSignal {
    pub source_id: String,
    pub source_uri: String,
    pub title: String,
    pub score: i64,
    pub comments: i64,
    pub created_at: i64,
    pub observed_length: usize,
    pub language: Option<String>,
    pub self_post: bool,
    pub nsfw: bool,
    pub author_deleted: bool,
    pub post_deleted: bool,
    pub crosspost: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RedditRawPage {
    pub signals: Vec<RedditRawSignal>,
    pub after: Option<String>,
    pub remaining: Option<f64>,
    pub reset_seconds: Option<u64>,
    pub etag: Option<String>,
}

pub trait RedditTransport {
    fn fetch(&self, query: &RedditSignalQuery) -> Result<RedditRawPage, RedditError>;
}

#[derive(Clone, PartialEq, Eq)]
pub struct RedditCredentials {
    client_id: String,
    client_secret: String,
    user_agent: String,
}

impl RedditCredentials {
    pub fn new(
        client_id: &str,
        client_secret: &str,
        user_agent: &str,
    ) -> Result<Self, RedditError> {
        if client_id.trim().is_empty()
            || client_secret.trim().is_empty()
            || user_agent.trim().is_empty()
        {
            return Err(RedditError::new(
                "credentials_invalid",
                "Reddit credentials and user agent are required",
            ));
        }
        Ok(Self {
            client_id: client_id.trim().to_owned(),
            client_secret: client_secret.trim().to_owned(),
            user_agent: user_agent.trim().to_owned(),
        })
    }

    pub fn client_id(&self) -> &str {
        &self.client_id
    }

    pub fn client_secret(&self) -> &str {
        &self.client_secret
    }

    pub fn user_agent(&self) -> &str {
        &self.user_agent
    }
}

impl std::fmt::Debug for RedditCredentials {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("RedditCredentials")
            .field("client_id", &"[REDACTED]")
            .field("client_secret", &"[REDACTED]")
            .field("user_agent", &self.user_agent)
            .finish()
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RedditHttpResponse {
    pub status: u16,
    pub json: serde_json::Value,
    pub headers: BTreeMap<String, String>,
}

pub trait RedditHttpClient {
    fn request_token(
        &self,
        credentials: &RedditCredentials,
    ) -> Result<RedditHttpResponse, RedditError>;

    fn request_listing(
        &self,
        bearer_token: &str,
        path: &str,
        query: &RedditSignalQuery,
        user_agent: &str,
    ) -> Result<RedditHttpResponse, RedditError>;
}

pub struct ReqwestRedditHttpClient {
    client: reqwest::blocking::Client,
}

impl ReqwestRedditHttpClient {
    const TOKEN_URL: &'static str = "https://www.reddit.com/api/v1/access_token";
    const API_ROOT: &'static str = "https://oauth.reddit.com";

    pub fn new() -> Result<Self, RedditError> {
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(20))
            .https_only(true)
            .build()
            .map_err(|_| RedditError::new("http_client_failed", "HTTP client is unavailable"))?;
        Ok(Self { client })
    }

    pub fn token_url(&self) -> &'static str {
        Self::TOKEN_URL
    }

    pub fn api_root(&self) -> &'static str {
        Self::API_ROOT
    }

    fn response(response: reqwest::blocking::Response) -> Result<RedditHttpResponse, RedditError> {
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
            .map_err(|_| RedditError::new("invalid_json", "Reddit returned invalid JSON"))?;
        Ok(RedditHttpResponse {
            status,
            json,
            headers,
        })
    }
}

impl RedditHttpClient for ReqwestRedditHttpClient {
    fn request_token(
        &self,
        credentials: &RedditCredentials,
    ) -> Result<RedditHttpResponse, RedditError> {
        let response = self
            .client
            .post(Self::TOKEN_URL)
            .basic_auth(credentials.client_id(), Some(credentials.client_secret()))
            .header(reqwest::header::USER_AGENT, credentials.user_agent())
            .form(&[("grant_type", "client_credentials")])
            .send()
            .map_err(|_| {
                RedditError::new("oauth_transport_failed", "Reddit OAuth is unavailable")
            })?;
        Self::response(response)
    }

    fn request_listing(
        &self,
        bearer_token: &str,
        path: &str,
        query: &RedditSignalQuery,
        user_agent: &str,
    ) -> Result<RedditHttpResponse, RedditError> {
        if !path.starts_with("/r/") || path.contains("..") {
            return Err(RedditError::new(
                "invalid_listing_path",
                "listing path is outside the Reddit API scope",
            ));
        }
        let mut parameters = vec![
            ("limit", query.limit.min(100).to_string()),
            ("raw_json", "1".to_owned()),
        ];
        if let Some(after) = &query.after {
            parameters.push(("after", after.clone()));
        }
        if let Some(time_filter) = &query.time_filter {
            let value = match time_filter {
                RedditTimeFilter::Hour => "hour",
                RedditTimeFilter::Day => "day",
                RedditTimeFilter::Week => "week",
                RedditTimeFilter::Month => "month",
                RedditTimeFilter::Year => "year",
                RedditTimeFilter::All => "all",
            };
            parameters.push(("t", value.to_owned()));
        }
        let response = self
            .client
            .get(format!("{}{path}", Self::API_ROOT))
            .bearer_auth(bearer_token)
            .header(reqwest::header::USER_AGENT, user_agent)
            .query(&parameters)
            .send()
            .map_err(|_| {
                RedditError::new("listing_transport_failed", "Reddit API is unavailable")
            })?;
        Self::response(response)
    }
}

pub struct OAuthRedditTransport<C: RedditHttpClient> {
    credentials: RedditCredentials,
    http: C,
    token: Mutex<Option<String>>,
}

impl<C: RedditHttpClient> OAuthRedditTransport<C> {
    pub fn new(credentials: RedditCredentials, http: C) -> Self {
        Self {
            credentials,
            http,
            token: Mutex::new(None),
        }
    }

    fn access_token(&self) -> Result<String, RedditError> {
        if let Some(token) = self
            .token
            .lock()
            .map_err(|_| RedditError::new("token_lock_failed", "token state is unavailable"))?
            .clone()
        {
            return Ok(token);
        }
        let response = self.http.request_token(&self.credentials)?;
        if response.status != 200 {
            return Err(RedditError::new(
                "oauth_failed",
                "Reddit OAuth returned a non-success status",
            ));
        }
        let token = response
            .json
            .get("access_token")
            .and_then(serde_json::Value::as_str)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| RedditError::new("oauth_invalid", "OAuth token is missing"))?
            .to_owned();
        *self
            .token
            .lock()
            .map_err(|_| RedditError::new("token_lock_failed", "token state is unavailable"))? =
            Some(token.clone());
        Ok(token)
    }
}

impl<C: RedditHttpClient> RedditTransport for OAuthRedditTransport<C> {
    fn fetch(&self, query: &RedditSignalQuery) -> Result<RedditRawPage, RedditError> {
        let token = self.access_token()?;
        let mut combined = RedditRawPage {
            signals: Vec::new(),
            after: None,
            remaining: None,
            reset_seconds: None,
            etag: None,
        };
        for subreddit in &query.subreddits {
            let path = build_listing_path(subreddit, &query.sort);
            let response =
                self.http
                    .request_listing(&token, &path, query, self.credentials.user_agent())?;
            if response.status == 429 {
                let retry = header(&response.headers, "retry-after")
                    .and_then(|value| value.parse::<u64>().ok())
                    .unwrap_or(60);
                return Err(RedditError::rate_limited(retry));
            }
            if response.status != 200 {
                return Err(RedditError::new(
                    "listing_failed",
                    "Reddit listing returned a non-success status",
                ));
            }
            let mut page = parse_listing_payload(
                &response.json,
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map_err(|_| RedditError::new("clock_error", "system clock is invalid"))?
                    .as_secs() as i64,
            )?;
            combined.signals.append(&mut page.signals);
            combined.after = page.after;
            combined.remaining = header(&response.headers, "x-ratelimit-remaining")
                .and_then(|value| value.parse::<f64>().ok());
            combined.reset_seconds = header(&response.headers, "x-ratelimit-reset")
                .and_then(|value| value.parse::<f64>().ok())
                .map(|value| value as u64);
            combined.etag = header(&response.headers, "etag").map(str::to_owned);
            if combined.signals.len() >= query.limit as usize {
                combined.signals.truncate(query.limit as usize);
                break;
            }
        }
        Ok(combined)
    }
}

fn header<'a>(headers: &'a BTreeMap<String, String>, name: &str) -> Option<&'a str> {
    headers
        .iter()
        .find(|(key, _)| key.eq_ignore_ascii_case(name))
        .map(|(_, value)| value.as_str())
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RedditQueryReceipt {
    pub receipt_id: String,
    pub query_hash: String,
    pub contract_reference: String,
    pub observed_at: u64,
    pub count: usize,
    pub after: Option<String>,
    pub remaining: Option<f64>,
    pub reset_seconds: Option<u64>,
    pub etag: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RedditSignalPage {
    pub schema_version: u8,
    pub signals: Vec<RedditRawSignal>,
    pub after: Option<String>,
    pub receipt: RedditQueryReceipt,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RedditError {
    code: String,
    message: String,
    retry_after_seconds: Option<u64>,
}

impl RedditError {
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
            message: "Reddit rate limit reached".into(),
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

impl std::fmt::Display for RedditError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for RedditError {}

pub struct RedditAuthority<T: RedditTransport> {
    policy: RedditAccessPolicy,
    transport: T,
}

impl<T: RedditTransport> RedditAuthority<T> {
    pub fn new(policy: RedditAccessPolicy, transport: T) -> Self {
        Self { policy, transport }
    }

    pub fn list_signals(&self, query: RedditSignalQuery) -> Result<RedditSignalPage, RedditError> {
        if !self.policy.enabled {
            return Err(RedditError::new(
                "disabled_by_policy",
                "Reddit access is disabled by policy",
            ));
        }
        validate_query(&query)?;
        let raw = self.transport.fetch(&query)?;
        let query_hash = hash_query(&query)?;
        let observed_at = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| RedditError::new("clock_error", "system clock is before Unix epoch"))?
            .as_secs();
        let contract_reference = self.policy.contract_reference.clone().ok_or_else(|| {
            RedditError::new("missing_contract_reference", "approval is incomplete")
        })?;
        let count = raw.signals.len();
        let after = raw.after.clone();
        Ok(RedditSignalPage {
            schema_version: 1,
            signals: raw.signals,
            after: after.clone(),
            receipt: RedditQueryReceipt {
                receipt_id: format!("rr_{}", &query_hash[..20]),
                query_hash,
                contract_reference,
                observed_at,
                count,
                after,
                remaining: raw.remaining,
                reset_seconds: raw.reset_seconds,
                etag: raw.etag,
            },
        })
    }
}

fn validate_query(query: &RedditSignalQuery) -> Result<(), RedditError> {
    if query.schema_version != 1 {
        return Err(RedditError::new(
            "invalid_schema",
            "unsupported query schema",
        ));
    }
    if query.subreddits.is_empty() || query.subreddits.len() > 20 {
        return Err(RedditError::new(
            "invalid_subreddit_count",
            "one to twenty subreddits are required",
        ));
    }
    if query.subreddits.iter().any(|subreddit| {
        subreddit.is_empty()
            || subreddit.len() > 21
            || !subreddit
                .chars()
                .all(|character| character.is_ascii_alphanumeric() || character == '_')
    }) {
        return Err(RedditError::new(
            "invalid_subreddit",
            "subreddit contains unsupported characters",
        ));
    }
    if query.time_filter.is_some() && query.sort != RedditSort::Top {
        return Err(RedditError::new(
            "invalid_time_filter",
            "time filter is supported only for top listings",
        ));
    }
    if !(1..=500).contains(&query.limit) {
        return Err(RedditError::new(
            "invalid_limit",
            "query limit must be between one and five hundred",
        ));
    }
    if query.after.as_ref().is_some_and(|cursor| {
        cursor.is_empty()
            || cursor.len() > 128
            || !cursor
                .chars()
                .all(|character| character.is_ascii_alphanumeric() || character == '_')
    }) {
        return Err(RedditError::new(
            "invalid_cursor",
            "cursor contains unsupported characters",
        ));
    }
    Ok(())
}

fn hash_query(query: &RedditSignalQuery) -> Result<String, RedditError> {
    let encoded = serde_json::to_vec(query)
        .map_err(|_| RedditError::new("query_serialization", "query cannot be serialized"))?;
    Ok(format!("{:x}", Sha256::digest(encoded)))
}

pub fn build_listing_path(subreddit: &str, sort: &RedditSort) -> String {
    let sort_name = match sort {
        RedditSort::New => "new",
        RedditSort::Hot => "hot",
        RedditSort::Top => "top",
    };
    format!("/r/{subreddit}/{sort_name}")
}

pub fn parse_listing_payload(
    payload: &serde_json::Value,
    now: i64,
) -> Result<RedditRawPage, RedditError> {
    let data = payload
        .get("data")
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| RedditError::new("invalid_response", "listing data is missing"))?;
    let children = data
        .get("children")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| RedditError::new("invalid_response", "listing children are missing"))?;
    let mut signals = Vec::new();
    for child in children {
        let Some(item) = child.get("data").and_then(serde_json::Value::as_object) else {
            continue;
        };
        let source_id = item
            .get("id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default()
            .to_owned();
        if source_id.is_empty() {
            continue;
        }
        let title = item
            .get("title")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default()
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
            .chars()
            .take(240)
            .collect::<String>();
        let body = item
            .get("selftext")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let observed_length = body.chars().count();
        let post_deleted = matches!(body, "[deleted]" | "[removed]")
            || item
                .get("removed_by_category")
                .is_some_and(|value| !value.is_null());
        let author_deleted = item
            .get("author")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|author| author == "[deleted]");
        let permalink = item
            .get("permalink")
            .and_then(serde_json::Value::as_str)
            .filter(|value| value.starts_with('/'))
            .unwrap_or_default();
        let created_at = item
            .get("created_utc")
            .and_then(serde_json::Value::as_f64)
            .map(|value| value as i64)
            .unwrap_or(now);
        signals.push(RedditRawSignal {
            source_id,
            source_uri: format!("https://www.reddit.com{permalink}"),
            title,
            score: item
                .get("score")
                .and_then(serde_json::Value::as_i64)
                .unwrap_or(0),
            comments: item
                .get("num_comments")
                .and_then(serde_json::Value::as_i64)
                .unwrap_or(0),
            created_at,
            observed_length,
            language: None,
            self_post: item
                .get("is_self")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false),
            nsfw: item
                .get("over_18")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or(false),
            author_deleted,
            post_deleted,
            crosspost: item
                .get("crosspost_parent")
                .is_some_and(|value| !value.is_null()),
        });
    }
    Ok(RedditRawPage {
        signals,
        after: data
            .get("after")
            .and_then(serde_json::Value::as_str)
            .map(str::to_owned),
        remaining: None,
        reset_seconds: None,
        etag: None,
    })
}
