from kronara.distribution import MetaPublisher, PublicationIntent, PublicationStatus


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

