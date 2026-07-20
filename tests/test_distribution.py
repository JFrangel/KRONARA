from kronara.distribution import (
    AuthorityMetaTransport,
    IdempotentReelsPublisher,
    MemoryIntentStore,
    MetaPublisher,
    PublicationIntent,
    PublicationReceipt,
    PublicationStatus,
)


class AmbiguousTransport:
    def __init__(self):
        self.uploads = 0

    def upload(self, intent):
        self.uploads += 1
        raise TimeoutError("remote outcome unknown")

    def find_by_idempotency_key(self, key):
        return {"remote_id": "fb_123", "status": "published"}


def test_meta_publisher_queries_remote_state_after_ambiguous_timeout():
    transport = AmbiguousTransport()
    publisher = MetaPublisher(transport)
    intent = PublicationIntent("episode_1", "variant_1", "facebook_reels", "idem_1")

    receipt = publisher.publish(intent)

    assert receipt.status is PublicationStatus.PUBLISHED
    assert receipt.remote_id == "fb_123"
    assert transport.uploads == 1


class CountingTransport:
    def __init__(self):
        self.uploads = 0

    def upload(self, intent):
        self.uploads += 1
        return {"status": "published", "remote_id": "fb_777"}

    def find_by_idempotency_key(self, key):
        return None


def _intent(key="idem_x"):
    return PublicationIntent("ep", "reel_9x16", "facebook_reels", key, video_ref="kronara://sha256/abc")


def test_idempotent_publisher_does_not_republish_a_live_intent():
    transport = CountingTransport()
    store = MemoryIntentStore()
    publisher = IdempotentReelsPublisher(MetaPublisher(transport), store)

    first = publisher.publish(_intent())
    second = publisher.publish(_intent())  # resumed run, same key

    assert first.status is PublicationStatus.PUBLISHED
    assert second.status is PublicationStatus.PUBLISHED
    assert transport.uploads == 1  # never posted twice


def test_idempotent_publisher_records_pending_then_final():
    store = MemoryIntentStore()
    publisher = IdempotentReelsPublisher(MetaPublisher(CountingTransport()), store)
    receipt = publisher.publish(_intent("idem_y"))
    assert store.get("idem_y") == receipt
    assert store.get("idem_y").status is PublicationStatus.PUBLISHED


class FakeAuthority:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def invoke(self, tool_id, arguments):
        self.calls.append((tool_id, arguments))
        return self.response


def test_authority_transport_calls_publication_publish():
    authority = FakeAuthority({"status": "published", "remote_id": "fb_999"})
    transport = AuthorityMetaTransport(authority)
    result = transport.upload(_intent("idem_z"))
    assert result["remote_id"] == "fb_999"
    assert authority.calls[0][0] == "publication.publish"
    assert authority.calls[0][1]["mode"] == "upload"


def test_authority_transport_reconcile_returns_none_when_no_remote():
    authority = FakeAuthority({"status": "not_configured"})
    transport = AuthorityMetaTransport(authority)
    assert transport.find_by_idempotency_key("idem_none") is None

