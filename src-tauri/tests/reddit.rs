use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use kronara_authority::reddit::{
    build_listing_path, parse_listing_payload, OAuthRedditTransport, RedditAccessPolicy,
    RedditAuthority, RedditCredentials, RedditError, RedditHttpClient, RedditHttpResponse,
    RedditRawPage, RedditRawSignal, RedditSignalQuery, RedditSort, RedditTimeFilter,
    RedditTransport, ReqwestRedditHttpClient,
};

#[derive(Clone)]
struct FakeTransport {
    calls: Arc<Mutex<usize>>,
    page: RedditRawPage,
}

impl RedditTransport for FakeTransport {
    fn fetch(&self, _query: &RedditSignalQuery) -> Result<RedditRawPage, RedditError> {
        *self.calls.lock().unwrap() += 1;
        Ok(self.page.clone())
    }
}

fn query() -> RedditSignalQuery {
    RedditSignalQuery {
        schema_version: 1,
        subreddits: vec!["Historias".into()],
        sort: RedditSort::Top,
        time_filter: Some(RedditTimeFilter::Week),
        after: None,
        limit: 25,
        include_nsfw: false,
    }
}

fn transport() -> FakeTransport {
    FakeTransport {
        calls: Arc::new(Mutex::new(0)),
        page: RedditRawPage {
            signals: vec![RedditRawSignal {
                source_id: "abc".into(),
                source_uri: "https://www.reddit.com/r/Historias/comments/abc".into(),
                title: "Una decisión inesperada".into(),
                score: 120,
                comments: 45,
                created_at: 100,
                observed_length: 840,
                language: Some("es".into()),
                self_post: true,
                nsfw: false,
                author_deleted: false,
                post_deleted: false,
                crosspost: false,
            }],
            after: Some("t3_next".into()),
            remaining: Some(58.0),
            reset_seconds: Some(42),
            etag: Some("listing-v1".into()),
        },
    }
}

#[test]
fn disabled_policy_makes_no_http_request() {
    let transport = transport();
    let calls = transport.calls.clone();
    let authority = RedditAuthority::new(RedditAccessPolicy::disabled(), transport);

    let result = authority.list_signals(query());

    assert_eq!(result.unwrap_err().code(), "disabled_by_policy");
    assert_eq!(*calls.lock().unwrap(), 0);
}

#[test]
fn approved_query_returns_safe_receipt_without_body_or_credentials() {
    let authority = RedditAuthority::new(
        RedditAccessPolicy::approved("reddit-contract-1").unwrap(),
        transport(),
    );

    let page = authority.list_signals(query()).unwrap();
    let encoded = serde_json::to_string(&page).unwrap();

    assert_eq!(page.signals.len(), 1);
    assert_eq!(page.after.as_deref(), Some("t3_next"));
    assert!(!encoded.contains("client_secret"));
    assert!(!encoded.contains("selftext"));
    assert!(!encoded.contains("body"));
    assert_eq!(page.receipt.contract_reference, "reddit-contract-1");
}

#[test]
fn query_validation_rejects_non_top_time_filter_and_unsafe_subreddit() {
    let authority = RedditAuthority::new(
        RedditAccessPolicy::approved("reddit-contract-1").unwrap(),
        transport(),
    );
    let mut invalid_time = query();
    invalid_time.sort = RedditSort::New;
    let mut invalid_subreddit = query();
    invalid_subreddit.subreddits = vec!["../secrets".into()];

    assert_eq!(
        authority.list_signals(invalid_time).unwrap_err().code(),
        "invalid_time_filter"
    );
    assert_eq!(
        authority
            .list_signals(invalid_subreddit)
            .unwrap_err()
            .code(),
        "invalid_subreddit"
    );
}

#[test]
fn official_listing_parser_discards_body_and_uses_fixed_path() {
    let payload = serde_json::json!({
        "data": {
            "after": "t3_next",
            "children": [{
                "data": {
                    "id": "abc",
                    "title": "Una decisión inesperada",
                    "selftext": "BODY THAT MUST DISAPPEAR",
                    "score": 120,
                    "num_comments": 45,
                    "created_utc": 100,
                    "permalink": "/r/Historias/comments/abc",
                    "is_self": true,
                    "over_18": false,
                    "author": "[deleted]",
                    "removed_by_category": null,
                    "crosspost_parent": null
                }
            }]
        }
    });

    let page = parse_listing_payload(&payload, 200).unwrap();
    let encoded = serde_json::to_string(&page.signals).unwrap();

    assert_eq!(page.after.as_deref(), Some("t3_next"));
    assert_eq!(page.signals[0].observed_length, 24);
    assert!(!encoded.contains("BODY THAT MUST DISAPPEAR"));
    assert_eq!(
        build_listing_path("Historias", &RedditSort::Top),
        "/r/Historias/top"
    );
}

#[derive(Clone, Default)]
struct FakeHttpClient {
    calls: Arc<Mutex<Vec<String>>>,
}

impl RedditHttpClient for FakeHttpClient {
    fn request_token(
        &self,
        _credentials: &RedditCredentials,
    ) -> Result<RedditHttpResponse, RedditError> {
        self.calls.lock().unwrap().push("token".into());
        Ok(RedditHttpResponse {
            status: 200,
            json: serde_json::json!({"access_token": "oauth-token", "expires_in": 3600}),
            headers: BTreeMap::new(),
        })
    }

    fn request_listing(
        &self,
        _bearer_token: &str,
        path: &str,
        _query: &RedditSignalQuery,
        _user_agent: &str,
    ) -> Result<RedditHttpResponse, RedditError> {
        self.calls.lock().unwrap().push(format!("listing:{path}"));
        Ok(RedditHttpResponse {
            status: 200,
            json: serde_json::json!({"data": {"after": null, "children": []}}),
            headers: BTreeMap::from([
                ("x-ratelimit-remaining".into(), "57.0".into()),
                ("x-ratelimit-reset".into(), "40".into()),
            ]),
        })
    }
}

#[test]
fn oauth_transport_owns_credentials_and_uses_official_endpoints() {
    let credentials = RedditCredentials::new("client", "super-secret", "kronara/0.4").unwrap();
    let http = FakeHttpClient::default();
    let calls = http.calls.clone();
    let transport = OAuthRedditTransport::new(credentials.clone(), http);

    let page = transport.fetch(&query()).unwrap();

    assert_eq!(page.remaining, Some(57.0));
    assert_eq!(
        calls.lock().unwrap().as_slice(),
        ["token", "listing:/r/Historias/top"]
    );
    assert!(!format!("{credentials:?}").contains("super-secret"));
}

#[test]
fn production_http_client_is_pinned_to_official_hosts() {
    let client = ReqwestRedditHttpClient::new().unwrap();

    assert_eq!(
        client.token_url(),
        "https://www.reddit.com/api/v1/access_token"
    );
    assert_eq!(client.api_root(), "https://oauth.reddit.com");
}
