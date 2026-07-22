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


def test_harvest_preserves_body_as_private_research_context():
    store = OpportunityStore(":memory:").initialize()
    store.harvest(
        [RssPost("nosleep", "The figure in my room", "l-body", "t", body="Full haunted thread body.")],
        now=100,
    )

    opportunity = store.take_next_for_subreddits(["nosleep"], now=101)

    assert opportunity is not None
    assert opportunity.body == "Full haunted thread body."
    store.close()


def test_harvest_skips_moderation_and_crisis_posts():
    store = OpportunityStore(":memory:").initialize()
    added = store.harvest(
        [
            RssPost("confession", "Community Updates", "l1", "t"),
            RssPost("TrueOffMyChest", "Sexual Assault, Consent, and Support Resources", "l2", "t"),
            RssPost("confession", "I stole groceries from a charity food drive", "l3", "t"),
        ],
        now=100,
    )

    assert added == 1
    opportunity = store.take_next(now=101)
    assert opportunity is not None
    assert opportunity.theme_hint == "I stole groceries from a charity food drive"
    store.close()


def test_harvest_preserves_sensitivity_per_post():
    store = OpportunityStore(":memory:").initialize()
    sensitive_posts = [
        RssPost("CPTSD", "How I finally understood my childhood", "l3", "t", sensitivity="real_experience_serious"),
        RssPost("ProRevenge", "I got my money back", "l4", "t", sensitivity="entertainment"),
    ]
    store.harvest(sensitive_posts, now=100)

    dispensed = {store.take_next(now=101).subreddit: None for _ in range(2)}
    pending_all = list(dispensed.keys())
    assert set(pending_all) == {"CPTSD", "ProRevenge"}
    store.close()


def test_take_next_returns_correct_sensitivity_per_opportunity():
    store = OpportunityStore(":memory:").initialize()
    store.harvest(
        [RssPost("domesticviolence", "unique title xyz", "l5", "t", sensitivity="real_experience_serious")],
        now=100,
    )
    opportunity = store.take_next(now=101)
    assert opportunity is not None
    assert opportunity.sensitivity == "real_experience_serious"
    store.close()


def test_default_sensitivity_is_entertainment_when_not_specified():
    store = OpportunityStore(":memory:").initialize()
    store.harvest([RssPost("stories", "a plain story title", "l6", "t")], now=100)
    opportunity = store.take_next(now=101)
    assert opportunity.sensitivity == "entertainment"
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


def test_take_next_for_subreddits_only_returns_matching_subreddits():
    store = OpportunityStore(":memory:").initialize()
    store.harvest(posts(), now=100)  # ProRevenge, AmItheAsshole

    result = store.take_next_for_subreddits(["AmItheAsshole"], now=101)

    assert result is not None
    assert result.subreddit == "AmItheAsshole"
    # The ProRevenge opportunity is untouched -- still pending for whichever
    # program actually reads that subreddit.
    assert store.count("new") == 1
    store.close()


def test_take_next_for_subreddits_ignores_other_programs_backlog():
    store = OpportunityStore(":memory:").initialize()
    store.harvest([RssPost("nosleep", "a horror story", "l7", "t")], now=100)

    result = store.take_next_for_subreddits(["ProRevenge"], now=101)

    assert result is None  # nothing pending for THIS program's subreddits
    assert store.count("new") == 1  # the nosleep opportunity is untouched
    store.close()


def test_take_next_for_subreddits_with_empty_list_returns_none():
    store = OpportunityStore(":memory:").initialize()
    store.harvest(posts(), now=100)
    assert store.take_next_for_subreddits([], now=101) is None
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
