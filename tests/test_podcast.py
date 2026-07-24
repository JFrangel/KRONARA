import xml.etree.ElementTree as ET

from kronara.podcast import build_rss


def test_build_rss_is_valid_xml_with_channel_and_items():
    rss = build_rss(
        title="Kronara — Cronicas de Justicia",
        description="Casos reales reconstruidos.",
        self_url="https://example.com/feed.xml",
        image_url="https://example.com/cover.png",
        episodes=[
            {
                "title": "El recibo de 3 dólares",
                "description": "Una mentira de quince años.",
                "audio_url": "https://example.com/ep1.mp3",
                "audio_bytes": 1234567,
                "duration_seconds": 95,
                "pub_ts": 1_700_000_000,
                "guid": "owned-1",
                "season": 1,
                "episode_number": 3,
            },
        ],
    )
    root = ET.fromstring(rss)  # must parse
    channel = root.find("channel")
    assert channel.findtext("title") == "Kronara — Cronicas de Justicia"
    item = channel.find("item")
    assert item.findtext("title") == "El recibo de 3 dólares"
    enclosure = item.find("enclosure")
    assert enclosure.get("url") == "https://example.com/ep1.mp3"
    assert enclosure.get("type") == "audio/mpeg"
    assert enclosure.get("length") == "1234567"
    # iTunes namespace tags are present.
    itunes = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
    assert item.findtext(f"{itunes}duration") == "01:35"
    assert item.findtext(f"{itunes}season") == "1"
    assert item.findtext(f"{itunes}episode") == "3"


def test_build_rss_escapes_and_handles_empty_feed():
    rss = build_rss(title="A & B <ok>", description="d", episodes=[])
    root = ET.fromstring(rss)  # escaping must keep it valid XML
    assert root.find("channel").findtext("title") == "A & B <ok>"
    assert root.find("channel").find("item") is None  # empty feed, no items


def test_duration_formats_hours_when_long():
    rss = build_rss(title="t", description="d", episodes=[
        {"title": "long", "audio_url": "u", "duration_seconds": 3725, "pub_ts": 0},
    ])
    itunes = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
    dur = ET.fromstring(rss).find("channel").find("item").findtext(f"{itunes}duration")
    assert dur == "1:02:05"
