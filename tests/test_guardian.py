from kronara.contracts import EvidenceRef
from kronara.guardian import Guardian


def test_guardian_rejects_claim_without_evidence():
    report = Guardian().verify_claims(["Facebook reel was published"], [])

    assert report.passed is False
    assert report.unverified_claims == ("Facebook reel was published",)


def test_guardian_accepts_claim_with_matching_evidence():
    evidence = EvidenceRef(
        evidence_id="ev_1",
        source_uri="meta://publication/123",
        supports=("Facebook reel was published",),
        confidence=1.0,
    )

    report = Guardian().verify_claims(["Facebook reel was published"], [evidence])

    assert report.passed is True

