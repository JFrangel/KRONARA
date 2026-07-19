import pytest

from kronara.reddit_client import (
    RateLimitError,
    RedditAccessPolicy,
    RedditClient,
    RedditCredentials,
    RedditPolicyDisabledError,
)


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_reddit_client_uses_oauth_and_returns_abstract_signals():
    http = FakeHttp(
        [
            {"status": 200, "json": {"access_token": "token", "expires_in": 3600}},
            {
                "status": 200,
                "json": {
                    "data": {
                        "children": [
                            {
                                "data": {
                                    "id": "abc",
                                    "title": "A locked room changed my family",
                                    "selftext": "This authored body must not survive extraction",
                                    "score": 300,
                                    "num_comments": 90,
                                    "created_utc": 100,
                                    "permalink": "/r/stories/abc",
                                }
                            }
                        ]
                    }
                },
            },
        ]
    )
    client = RedditClient(
        RedditCredentials("client", "secret", "kronara/0.2 contact@example.com"),
        http=http,
        clock=lambda: 200,
        policy=RedditAccessPolicy.approved("reddit-contract-1"),
    )

    signals = client.hot_signals("stories", limit=10)

    assert len(signals) == 1
    assert signals[0].source_text is None
    assert "authored body" not in repr(signals[0])
    assert http.calls[0][2]["basic_auth"] == ("client", "secret")
    assert http.calls[1][2]["headers"]["Authorization"] == "Bearer token"


def test_reddit_client_surfaces_retry_after_on_rate_limit():
    http = FakeHttp(
        [
            {"status": 200, "json": {"access_token": "token", "expires_in": 3600}},
            {"status": 429, "json": {}, "headers": {"Retry-After": "30"}},
        ]
    )
    client = RedditClient(
        RedditCredentials("client", "secret", "agent"),
        http=http,
        clock=lambda: 200,
        policy=RedditAccessPolicy.approved("reddit-contract-1"),
    )

    with pytest.raises(RateLimitError) as error:
        client.hot_signals("stories")

    assert error.value.retry_after_seconds == 30


def test_reddit_is_disabled_by_policy_until_access_is_explicitly_approved():
    http = FakeHttp([])
    client = RedditClient(
        RedditCredentials("client", "secret", "agent"),
        http=http,
        clock=lambda: 200,
    )

    with pytest.raises(RedditPolicyDisabledError) as error:
        client.list_signals("stories", sort="new")

    assert error.value.status == "disabled_by_policy"
    assert http.calls == []


def test_reddit_listing_supports_top_time_filter_and_cache_metadata():
    http = FakeHttp(
        [
            {"status": 200, "json": {"access_token": "token", "expires_in": 3600}},
            {
                "status": 200,
                "json": {"data": {"children": []}},
                "headers": {
                    "ETag": '"listing-v1"',
                    "Cache-Control": "private, max-age=60",
                    "X-Ratelimit-Remaining": "58.0",
                    "X-Ratelimit-Reset": "42",
                },
            },
        ]
    )
    client = RedditClient(
        RedditCredentials("client", "secret", "agent"),
        http=http,
        clock=lambda: 200,
        policy=RedditAccessPolicy.approved("reddit-contract-1"),
    )

    listing = client.list_signals(
        "stories",
        sort="top",
        time_filter="week",
        limit=10,
        etag='"listing-v0"',
    )

    request = http.calls[1]
    assert request[1].endswith("/r/stories/top")
    assert request[2]["params"]["t"] == "week"
    assert request[2]["headers"]["If-None-Match"] == '"listing-v0"'
    assert listing.cache.etag == '"listing-v1"'
    assert listing.cache.cache_control == "private, max-age=60"
    assert listing.rate_limit.remaining == 58.0
    assert listing.rate_limit.reset_seconds == 42


@pytest.mark.parametrize("sort", ["new", "hot", "top"])
def test_reddit_listing_accepts_supported_orderings(sort):
    http = FakeHttp(
        [
            {"status": 200, "json": {"access_token": "token", "expires_in": 3600}},
            {"status": 200, "json": {"data": {"children": []}}, "headers": {}},
        ]
    )
    client = RedditClient(
        RedditCredentials("client", "secret", "agent"),
        http=http,
        clock=lambda: 200,
        policy=RedditAccessPolicy.approved("reddit-contract-1"),
    )

    listing = client.list_signals("stories", sort=sort)

    assert listing.sort == sort


def test_reddit_rejects_time_filter_for_non_top_listing():
    client = RedditClient(
        RedditCredentials("client", "secret", "agent"),
        http=FakeHttp([]),
        clock=lambda: 200,
        policy=RedditAccessPolicy.approved("reddit-contract-1"),
    )

    with pytest.raises(ValueError, match="time_filter"):
        client.list_signals("stories", sort="new", time_filter="week")


def test_reddit_listing_passes_cursor_and_returns_next_cursor():
    http = FakeHttp(
        [
            {"status": 200, "json": {"access_token": "token", "expires_in": 3600}},
            {
                "status": 200,
                "json": {"data": {"children": [], "after": "t3_next"}},
                "headers": {},
            },
        ]
    )
    client = RedditClient(
        RedditCredentials("client", "secret", "agent"),
        http=http,
        clock=lambda: 200,
        policy=RedditAccessPolicy.approved("reddit-contract-1"),
    )

    listing = client.list_signals("stories", sort="new", after="t3_previous")

    assert http.calls[1][2]["params"]["after"] == "t3_previous"
    assert listing.after == "t3_next"
