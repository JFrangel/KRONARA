use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use kronara_authority::pexels::{
    parse_search_payload, DirectPexelsTransport, PexelsAccessPolicy, PexelsAuthority,
    PexelsCredentials, PexelsError, PexelsHttpClient, PexelsHttpResponse, PexelsOrientation,
    PexelsRawPage, PexelsRawVideo, PexelsTransport, PexelsVideoQuery, ReqwestPexelsHttpClient,
};

#[derive(Clone)]
struct FakeTransport {
    calls: Arc<Mutex<usize>>,
    page: PexelsRawPage,
}

impl PexelsTransport for FakeTransport {
    fn search(&self, _query: &PexelsVideoQuery) -> Result<PexelsRawPage, PexelsError> {
        *self.calls.lock().unwrap() += 1;
        Ok(self.page.clone())
    }
}

fn query() -> PexelsVideoQuery {
    PexelsVideoQuery {
        schema_version: 1,
        query: "fog abandoned hallway".into(),
        orientation: Some(PexelsOrientation::Portrait),
        per_page: 10,
        page: 1,
    }
}

fn transport() -> FakeTransport {
    FakeTransport {
        calls: Arc::new(Mutex::new(0)),
        page: PexelsRawPage {
            videos: vec![PexelsRawVideo {
                source_id: "2499611".into(),
                source_uri: "https://www.pexels.com/video/2499611/".into(),
                download_url: "https://videos.pexels.com/video-files/2499611/hd.mp4".into(),
                width: 1080,
                height: 1920,
                duration_seconds: 20,
                photographer: "Someone".into(),
            }],
            next_page: Some(2),
            remaining: Some(190.0),
            reset_seconds: Some(3600),
        },
    }
}

#[test]
fn disabled_policy_makes_no_http_request() {
    let transport = transport();
    let calls = transport.calls.clone();
    let authority = PexelsAuthority::new(PexelsAccessPolicy::disabled(), transport);

    let result = authority.search_videos(query());

    assert_eq!(result.unwrap_err().code(), "disabled_by_policy");
    assert_eq!(*calls.lock().unwrap(), 0);
}

#[test]
fn approved_query_returns_safe_receipt_without_credentials() {
    let authority = PexelsAuthority::new(
        PexelsAccessPolicy::approved("pexels-contract-1").unwrap(),
        transport(),
    );

    let page = authority.search_videos(query()).unwrap();
    let encoded = serde_json::to_string(&page).unwrap();

    assert_eq!(page.videos.len(), 1);
    assert_eq!(page.next_page, Some(2));
    assert!(!encoded.contains("api_key"));
    assert_eq!(page.receipt.contract_reference, "pexels-contract-1");
}

#[test]
fn query_validation_rejects_empty_text_and_out_of_range_per_page() {
    let authority = PexelsAuthority::new(
        PexelsAccessPolicy::approved("pexels-contract-1").unwrap(),
        transport(),
    );
    let mut empty_query = query();
    empty_query.query = "   ".into();
    let mut too_many = query();
    too_many.per_page = 200;

    assert_eq!(
        authority.search_videos(empty_query).unwrap_err().code(),
        "invalid_query_text"
    );
    assert_eq!(
        authority.search_videos(too_many).unwrap_err().code(),
        "invalid_per_page"
    );
}

#[test]
fn parser_selects_the_hd_mp4_file_and_discards_others() {
    let payload = serde_json::json!({
        "videos": [{
            "id": 2499611,
            "url": "https://www.pexels.com/video/2499611/",
            "duration": 20,
            "user": {"name": "Someone"},
            "video_files": [
                {"quality": "sd", "file_type": "video/mp4", "width": 640, "height": 1138, "link": "sd.mp4"},
                {"quality": "hd", "file_type": "video/mp4", "width": 1080, "height": 1920, "link": "hd.mp4"},
                {"quality": "hd", "file_type": "video/webm", "width": 1080, "height": 1920, "link": "hd.webm"}
            ]
        }]
    });

    let page = parse_search_payload(&payload).unwrap();

    assert_eq!(page.videos.len(), 1);
    assert_eq!(page.videos[0].download_url, "hd.mp4");
    assert_eq!(page.videos[0].width, 1080);
}

#[test]
fn parser_skips_a_video_with_no_usable_mp4_file() {
    let payload = serde_json::json!({
        "videos": [
            {
                "id": 1,
                "url": "https://www.pexels.com/video/1/",
                "duration": 10,
                "user": {"name": "A"},
                "video_files": [
                    {"quality": "hd", "file_type": "video/webm", "width": 1080, "height": 1920, "link": "only.webm"}
                ]
            },
            {
                "id": 2,
                "url": "https://www.pexels.com/video/2/",
                "duration": 12,
                "user": {"name": "B"},
                "video_files": [
                    {"quality": "sd", "file_type": "video/mp4", "width": 640, "height": 1138, "link": "sd.mp4"}
                ]
            }
        ]
    });

    let page = parse_search_payload(&payload).unwrap();

    assert_eq!(page.videos.len(), 1);
    assert_eq!(page.videos[0].source_id, "2");
}

#[derive(Clone, Default)]
struct FakeHttpClient {
    calls: Arc<Mutex<Vec<String>>>,
}

impl PexelsHttpClient for FakeHttpClient {
    fn request_search(
        &self,
        _credentials: &PexelsCredentials,
        query: &PexelsVideoQuery,
    ) -> Result<PexelsHttpResponse, PexelsError> {
        self.calls
            .lock()
            .unwrap()
            .push(format!("search:{}", query.query));
        Ok(PexelsHttpResponse {
            status: 200,
            json: serde_json::json!({"videos": [], "next_page": null}),
            headers: BTreeMap::from([
                ("x-ratelimit-remaining".into(), "199.0".into()),
                ("x-ratelimit-reset".into(), "3600".into()),
            ]),
        })
    }
}

#[test]
fn direct_transport_owns_credentials_and_reads_rate_limit_headers() {
    let credentials = PexelsCredentials::new("super-secret-key").unwrap();
    let http = FakeHttpClient::default();
    let calls = http.calls.clone();
    let transport = DirectPexelsTransport::new(credentials.clone(), http);

    let page = transport.search(&query()).unwrap();

    assert_eq!(page.remaining, Some(199.0));
    assert_eq!(
        calls.lock().unwrap().as_slice(),
        ["search:fog abandoned hallway"]
    );
    assert!(!format!("{credentials:?}").contains("super-secret-key"));
}

#[test]
fn production_http_client_is_pinned_to_the_official_host() {
    let client = ReqwestPexelsHttpClient::new().unwrap();

    assert_eq!(client.api_root(), "https://api.pexels.com/videos/search");
}
