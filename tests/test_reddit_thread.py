import json

from kronara.reddit_thread import RedditThreadReader, ThreadUpdate, extract_updates


def test_extract_updates_splits_body_from_update_blocks():
    selftext = (
        "Encontré una cámara escondida en el detector de humo.\n\n"
        "UPDATE: revisé la memoria y había grabaciones de seis meses.\n\n"
        "EDIT 2: la policía se llevó el equipo esta mañana."
    )
    body, updates = extract_updates(selftext)
    assert body == "Encontré una cámara escondida en el detector de humo."
    assert [u.label for u in updates] == ["UPDATE", "EDIT 2"]
    assert "seis meses" in updates[0].text
    assert all(isinstance(u, ThreadUpdate) and u.source == "selftext" for u in updates)


def test_extract_updates_returns_empty_when_no_markers():
    body, updates = extract_updates("Solo el relato original, sin novedades.")
    assert body == "Solo el relato original, sin novedades."
    assert updates == ()


def _canned_thread(**post):
    base = {
        "id": "abc123",
        "subreddit": "nosleep",
        "title": "La cámara en el detector de humo",
        "selftext": "Cuerpo original.\n\nUPDATE: apareció el responsable.",
        "edited": 1_700_000_000,
        "author": "case_op",
    }
    base.update(post)
    return [
        {"data": {"children": [{"data": base}]}},
        {
            "data": {
                "children": [
                    {"data": {"author": "case_op", "body": "Gracias por los consejos, aquí va lo que pasó después: " + "x" * 130}},
                    {"data": {"author": "otro_usuario", "body": "esto es un comentario ajeno bastante largo " + "y" * 130}},
                    {"data": {"author": "case_op", "body": "corto"}},
                ]
            }
        },
    ]


def test_fetch_parses_body_updates_and_op_followups():
    payload = json.dumps(_canned_thread())
    reader = RedditThreadReader(transport=lambda url: (200, payload))
    detail = reader.fetch("https://www.reddit.com/r/nosleep/comments/abc123/titulo/")
    assert detail is not None
    assert detail.thread_id == "abc123"
    assert detail.subreddit == "nosleep"
    assert detail.body == "Cuerpo original."
    assert [u.label for u in detail.updates] == ["UPDATE"]
    assert detail.edited is True
    assert detail.has_updates
    # Only the OP's substantive follow-up survives; foreign + one-liner are dropped.
    assert len(detail.op_followups) == 1
    assert "lo que pasó después" in detail.op_followups[0]
    assert detail.author == "case_op"


def test_json_url_builds_from_permalink_or_bare_id():
    reader = RedditThreadReader()
    assert reader._json_url("https://www.reddit.com/r/x/comments/id/t/?utm=1") == "https://www.reddit.com/r/x/comments/id/t.json"
    assert reader._json_url("xyz789") == "https://www.reddit.com/comments/xyz789.json"


def test_fetch_returns_none_on_error_status_and_bad_payload():
    assert RedditThreadReader(transport=lambda url: (404, "")).fetch("id") is None
    assert RedditThreadReader(transport=lambda url: (200, "not json")).fetch("id") is None
    assert RedditThreadReader(transport=lambda url: (200, "{}")).fetch("id") is None


def test_fetch_retries_on_429_then_gives_up():
    calls = {"n": 0}

    def flaky(url):
        calls["n"] += 1
        return (429, "")

    reader = RedditThreadReader(transport=flaky, max_retries=3, backoff_base=0.0)
    reader._sleep = lambda _s: None
    assert reader.fetch("id") is None
    assert calls["n"] == 3


def test_build_source_case_flattens_body_updates_and_followups():
    from kronara.reddit_thread import ThreadDetail, ThreadUpdate, build_source_case

    detail = ThreadDetail(
        thread_id="id", subreddit="nosleep", title="t",
        body="Cuerpo original del caso.", edited=True,
        updates=(ThreadUpdate("UPDATE", "apareció el responsable.", "selftext"),),
        op_followups=("aquí lo que pasó después según el autor",),
        author="op",
    )
    case = build_source_case(detail)
    assert "Cuerpo original del caso." in case
    assert "[UPDATE] apareció el responsable." in case
    assert "[SEGUIMIENTO DEL AUTOR] aquí lo que pasó después" in case
    # El nombre del autor nunca viaja en el material del caso.
    assert "op" not in case.split()


def test_build_source_case_empty_when_no_body():
    from kronara.reddit_thread import build_source_case

    assert build_source_case(None) == ""
