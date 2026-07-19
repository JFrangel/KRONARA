from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from kronara.trends import RedditSignalExtractor, SourcePost, TrendSignal


@dataclass(frozen=True)
class RedditCredentials:
    client_id: str
    client_secret: str
    user_agent: str


class RateLimitError(RuntimeError):
    def __init__(self, retry_after_seconds: int):
        super().__init__(f"Reddit rate limit; retry after {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


class HttpTransport(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]: ...


class HttpxTransport:
    def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        import httpx

        basic_auth = kwargs.pop("basic_auth", None)
        response = httpx.request(method, url, auth=basic_auth, timeout=20.0, **kwargs)
        return {
            "status": response.status_code,
            "json": response.json() if response.content else {},
            "headers": dict(response.headers),
        }


class RedditClient:
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    API_ROOT = "https://oauth.reddit.com"

    def __init__(
        self,
        credentials: RedditCredentials,
        http: HttpTransport | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.credentials = credentials
        self.http = http or HttpxTransport()
        self.clock = clock
        self._token: str | None = None
        self._token_expires_at = 0.0

    def _access_token(self) -> str:
        now = self.clock()
        if self._token and now < self._token_expires_at:
            return self._token
        response = self.http.request(
            "POST",
            self.TOKEN_URL,
            basic_auth=(self.credentials.client_id, self.credentials.client_secret),
            headers={"User-Agent": self.credentials.user_agent},
            data={"grant_type": "client_credentials"},
        )
        if response["status"] != 200:
            raise RuntimeError(f"Reddit OAuth failed with status {response['status']}")
        payload = response["json"]
        self._token = str(payload["access_token"])
        self._token_expires_at = now + max(0, int(payload.get("expires_in", 3600)) - 60)
        return self._token

    def hot_signals(self, subreddit: str, limit: int = 25) -> list[TrendSignal]:
        token = self._access_token()
        response = self.http.request(
            "GET",
            f"{self.API_ROOT}/r/{subreddit}/hot",
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": self.credentials.user_agent,
            },
            params={"limit": min(max(limit, 1), 100), "raw_json": 1},
        )
        if response["status"] == 429:
            retry_after = int(response.get("headers", {}).get("Retry-After", 60))
            raise RateLimitError(retry_after)
        if response["status"] != 200:
            raise RuntimeError(f"Reddit API failed with status {response['status']}")
        extractor = RedditSignalExtractor()
        now = int(self.clock())
        signals: list[TrendSignal] = []
        for child in response["json"].get("data", {}).get("children", []):
            data = child.get("data", {})
            post = SourcePost(
                source_id=str(data.get("id", "")),
                title=str(data.get("title", "")),
                body=str(data.get("selftext", "")),
                score=int(data.get("score", 0)),
                comments=int(data.get("num_comments", 0)),
                created_at=int(data.get("created_utc", now)),
                source_uri=f"https://www.reddit.com{data.get('permalink', '')}",
            )
            if post.source_id:
                signals.append(extractor.extract(post, now=now))
        return signals

