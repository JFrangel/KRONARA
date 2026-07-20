from kronara.reddit_rss import RedditRssReader, RssPost

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Notice: Judgement Bot is down</title>
    <link href="https://reddit.com/r/AITA/x1"/>
    <published>2026-07-19T10:00:00+00:00</published>
  </entry>
  <entry>
    <title>My sister sold my late mother's ring behind my back</title>
    <link href="https://reddit.com/r/AITA/x2"/>
    <published>2026-07-19T11:00:00+00:00</published>
  </entry>
</feed>
"""


def test_parses_feed_and_skips_meta_posts():
    reader = RedditRssReader(transport=lambda url: (200, ATOM_FEED))
    reader._sleep = lambda _s: None
    posts = reader.fetch_subreddit("AmItheAsshole")
    titles = [p.title for p in posts]
    assert "My sister sold my late mother's ring behind my back" in titles
    # trending() filters meta/stickied posts.
    story_posts = reader.trending(["AmItheAsshole"], max_subs=1)
    assert all("Notice:" not in p.title for p in story_posts)
    assert len(story_posts) == 1


def test_backoff_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def transport(url):
        calls["n"] += 1
        return (429, "") if calls["n"] == 1 else (200, ATOM_FEED)

    reader = RedditRssReader(transport=transport, max_retries=3)
    reader._sleep = lambda _s: None
    posts = reader.fetch_subreddit("ProRevenge")
    assert calls["n"] == 2
    assert len(posts) == 2


def test_gives_up_after_persistent_429():
    reader = RedditRssReader(transport=lambda url: (429, ""), max_retries=3)
    reader._sleep = lambda _s: None
    assert reader.fetch_subreddit("confessions") == []


def test_rsspost_shape():
    p = RssPost("AITA", "t", "l", "2026")
    assert p.subreddit == "AITA" and p.title == "t"
