from kronara.trends import RedditSignalExtractor, SourcePost


def test_reddit_extractor_keeps_abstract_signal_not_story_body():
    post = SourcePost(
        source_id="r1",
        title="A locked room changed my family",
        body="A long user-authored story that must not be stored or copied.",
        score=250,
        comments=80,
        created_at=100,
        source_uri="reddit://r1",
    )

    signal = RedditSignalExtractor().extract(post, now=200)

    assert signal.source_id == "r1"
    assert signal.source_text is None
    assert "long user-authored" not in repr(signal)
    assert signal.velocity > 0

