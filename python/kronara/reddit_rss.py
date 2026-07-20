"""No-credential Reddit reading via public RSS feeds.

The official API needs a registered app (client_id/secret). When you don't want
that, Reddit's public RSS feeds still expose post titles for a subreddit with no
login and no password — which is all the pipeline needs (it works from the
abstract title pattern, never the source body). Reddit rate-limits these feeds
per IP, so this reader backs off on 429 and rotates through subreddits politely;
it is meant for an agent that reads a couple of subs per run, not for hammering.

This is a compliant read of a public feed — it is NOT logged-in scraping.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

ATOM = {"a": "http://www.w3.org/2005/Atom"}

DEFAULT_UA = "windows:kronara:v0.6 (public rss reader)"

# Stickied / meta / mod posts to skip — they are not story material.
_SKIP_MARKERS = (
    "notice:",
    "megathread",
    "open forum",
    "quarterly",
    "monthly",
    "weekly",
    "rules",
    "[meta]",
    "announcement",
    "mod ",
    "sticky",
    "judgement bot",
)


@dataclass(frozen=True)
class RssPost:
    subreddit: str
    title: str
    link: str
    published: str
    # "entertainment" | "real_experience_serious" — see knowledge/reddit-sources/.
    sensitivity: str = "entertainment"


def _is_story(title: str) -> bool:
    low = title.casefold()
    return not any(marker in low for marker in _SKIP_MARKERS)


class RedditRssReader:
    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_UA,
        per_sub_delay: float = 8.0,
        max_retries: int = 3,
        backoff_base: float = 10.0,
        transport=None,
    ):
        self.user_agent = user_agent
        self.per_sub_delay = per_sub_delay
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        # Injectable for tests: callable(url) -> (status, text).
        self._transport = transport
        self._sleep = time.sleep

    def _get(self, url: str) -> tuple[int, str]:
        if self._transport is not None:
            return self._transport(url)
        response = httpx.get(
            url, headers={"User-Agent": self.user_agent}, timeout=20, follow_redirects=True
        )
        return response.status_code, response.text

    def fetch_subreddit(self, subreddit: str, *, limit: int = 8) -> list[RssPost]:
        url = f"https://www.reddit.com/r/{subreddit}/hot/.rss?limit={limit}"
        for attempt in range(self.max_retries):
            status, text = self._get(url)
            if status == 200:
                return self._parse(subreddit, text)
            if status == 429 and attempt < self.max_retries - 1:
                self._sleep(self.backoff_base * (attempt + 1))
                continue
            break
        return []

    def trending(self, subreddits: list[str], *, max_subs: int = 2, per_sub: int = 8) -> list[RssPost]:
        """Read up to ``max_subs`` subreddits politely and return story posts."""
        posts: list[RssPost] = []
        read = 0
        for index, sub in enumerate(subreddits):
            if read >= max_subs:
                break
            if index:
                self._sleep(self.per_sub_delay)
            found = [post for post in self.fetch_subreddit(sub, limit=per_sub) if _is_story(post.title)]
            if found:
                posts.extend(found)
                read += 1
        return posts

    @staticmethod
    def _parse(subreddit: str, text: str) -> list[RssPost]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        posts: list[RssPost] = []
        for entry in root.findall("a:entry", ATOM):
            title_el = entry.find("a:title", ATOM)
            link_el = entry.find("a:link", ATOM)
            published_el = entry.find("a:published", ATOM)
            title = (title_el.text or "").strip() if title_el is not None else ""
            link = link_el.get("href", "") if link_el is not None else ""
            published = (published_el.text or "") if published_el is not None else ""
            if title:
                posts.append(RssPost(subreddit, title, link, published))
        return posts
