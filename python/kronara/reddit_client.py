from __future__ import annotations

import time
from dataclasses import dataclass
import re
from typing import Any, Callable, Literal, Protocol

from kronara.trends import RedditSignalExtractor, SourcePost, TrendSignal


@dataclass(frozen=True)
class RedditCredentials:
    client_id: str
    client_secret: str
    user_agent: str


@dataclass(frozen=True)
class RedditAccessPolicy:
    status: Literal["approved", "disabled_by_policy"] = "disabled_by_policy"
    contract_reference: str | None = None

    @classmethod
    def approved(cls, contract_reference: str) -> "RedditAccessPolicy":
        if not contract_reference.strip():
            raise ValueError("contract_reference is required for approved Reddit access")
        return cls(status="approved", contract_reference=contract_reference)


class RedditPolicyDisabledError(RuntimeError):
    def __init__(self):
        self.status = "disabled_by_policy"
        super().__init__("Reddit access is disabled by policy")


@dataclass(frozen=True)
class CacheMetadata:
    etag: str | None
    cache_control: str | None
    not_modified: bool = False


@dataclass(frozen=True)
class RateLimitMetadata:
    remaining: float | None
    reset_seconds: int | None


@dataclass(frozen=True)
class RedditListing:
    sort: Literal["new", "hot", "top"]
    time_filter: str | None
    signals: tuple[TrendSignal, ...]
    cache: CacheMetadata
    rate_limit: RateLimitMetadata


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
        policy: RedditAccessPolicy | None = None,
    ):
        self.credentials = credentials
        self.http = http or HttpxTransport()
        self.clock = clock
        self.policy = policy or RedditAccessPolicy()
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
        return list(self.list_signals(subreddit, sort="hot", limit=limit).signals)

    def list_signals(
        self,
        subreddit: str,
        *,
        sort: Literal["new", "hot", "top"] = "hot",
        time_filter: str | None = None,
        limit: int = 25,
        etag: str | None = None,
    ) -> RedditListing:
        if self.policy.status != "approved":
            raise RedditPolicyDisabledError()
        if sort not in {"new", "hot", "top"}:
            raise ValueError("unsupported Reddit sort")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,21}", subreddit):
            raise ValueError("invalid subreddit")
        if time_filter is not None:
            if sort != "top":
                raise ValueError("time_filter is only supported for top listings")
            if time_filter not in {"hour", "day", "week", "month", "year", "all"}:
                raise ValueError("unsupported time_filter")
        token = self._access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": self.credentials.user_agent,
        }
        if etag:
            headers["If-None-Match"] = etag
        params: dict[str, Any] = {"limit": min(max(limit, 1), 100), "raw_json": 1}
        if time_filter is not None:
            params["t"] = time_filter
        response = self.http.request(
            "GET",
            f"{self.API_ROOT}/r/{subreddit}/{sort}",
            headers=headers,
            params=params,
        )
        response_headers = response.get("headers", {})
        if response["status"] == 429:
            retry_after = int(self._header(response_headers, "Retry-After") or 60)
            raise RateLimitError(retry_after)
        cache = CacheMetadata(
            etag=self._header(response_headers, "ETag"),
            cache_control=self._header(response_headers, "Cache-Control"),
            not_modified=response["status"] == 304,
        )
        rate_limit = RateLimitMetadata(
            remaining=self._optional_float(self._header(response_headers, "X-Ratelimit-Remaining")),
            reset_seconds=self._optional_int(self._header(response_headers, "X-Ratelimit-Reset")),
        )
        if response["status"] == 304:
            return RedditListing(sort, time_filter, (), cache, rate_limit)
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
        return RedditListing(sort, time_filter, tuple(signals), cache, rate_limit)

    @staticmethod
    def _header(headers: dict[str, Any], name: str) -> str | None:
        lowered = name.lower()
        for key, value in headers.items():
            if key.lower() == lowered:
                return str(value)
        return None

    @staticmethod
    def _optional_float(value: str | None) -> float | None:
        return float(value) if value is not None else None

    @staticmethod
    def _optional_int(value: str | None) -> int | None:
        return int(float(value)) if value is not None else None
