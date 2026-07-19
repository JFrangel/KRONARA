import pytest

from kronara.reddit_client import RateLimitError, RedditClient, RedditCredentials


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
        RedditCredentials("client", "secret", "agent"), http=http, clock=lambda: 200
    )

    with pytest.raises(RateLimitError) as error:
        client.hot_signals("stories")

    assert error.value.retry_after_seconds == 30

