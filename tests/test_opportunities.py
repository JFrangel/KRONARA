from kronara.opportunities import OpportunityStore, StoryLedger
from kronara.reddit_rss import RssPost


def posts():
    return [
        RssPost("ProRevenge", "My boss stole my commission so I took the client list", "l1", "t"),
        RssPost("AmItheAsshole", "AITA for exposing my brother's secret at dinner", "l2", "t"),
    ]


def test_harvest_saves_and_dedupes():
    store = OpportunityStore(":memory:").initialize()
    assert store.harvest(posts(), now=100) == 2
    assert store.harvest(posts(), now=200) == 0  # same posts -> nothing new
    assert store.count() == 2
    assert store.count("new") == 2
    store.close()


def test_take_next_dispenses_each_once():
    store = OpportunityStore(":memory:").initialize()
    store.harvest(posts(), now=100)
    first = store.take_next(now=101)
    second = store.take_next(now=102)
    third = store.take_next(now=103)
    assert first is not None and second is not None
    assert first.opportunity_id != second.opportunity_id
    assert third is None  # both consumed
    assert store.count("used") == 2
    store.close()


def test_ledger_flags_near_duplicate_of_a_different_series():
    ledger = StoryLedger(":memory:", threshold=0.6).initialize()
    ledger.record("s1", "Una restauradora descubre un audio que divide a su familia por la herencia",
                  series_id="serie-a", now=100)
    # Almost the same story, different series -> repeat.
    assert ledger.is_repeat(
        "Una restauradora descubre un audio que divide a su familia por una herencia",
        series_id="serie-b",
    ) is True
    # Clearly different story -> not a repeat.
    assert ledger.is_repeat(
        "Un astronauta repara una antena en la oscuridad de la estacion espacial",
        series_id="serie-c",
    ) is False


def test_ledger_allows_same_series_continuation():
    ledger = StoryLedger(":memory:", threshold=0.6).initialize()
    ledger.record("s1p1", "Mariana escucha el cassette del padre sobre la herencia y el testamento",
                  series_id="herencia", now=100)
    # Part 2 of the SAME series shares canon -> must NOT be flagged as a repeat.
    assert ledger.is_repeat(
        "Mariana escucha el cassette del padre sobre la herencia y el testamento oculto",
        series_id="herencia",
    ) is False
    ledger.close()
