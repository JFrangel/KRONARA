from kronara.contracts import AutonomyMode, AutonomyPolicy, RiskDecision, RiskLevel
from kronara.policy import AutonomyGuard


def test_full_auto_allows_low_risk_action():
    guard = AutonomyGuard(AutonomyPolicy(mode=AutonomyMode.FULL_AUTO))

    decision = guard.authorize("publish", RiskDecision(level=RiskLevel.LOW))

    assert decision.allowed is True
    assert decision.requires_human is False


def test_full_auto_blocks_non_overridable_rights_failure():
    guard = AutonomyGuard(AutonomyPolicy(mode=AutonomyMode.FULL_AUTO))

    decision = guard.authorize(
        "publish",
        RiskDecision(level=RiskLevel.CRITICAL, codes=("rights_insufficient",)),
    )

    assert decision.allowed is False
    assert decision.reason == "rights_insufficient"


def test_manual_requires_human_for_publication():
    guard = AutonomyGuard(AutonomyPolicy(mode=AutonomyMode.MANUAL))

    decision = guard.authorize("publish", RiskDecision(level=RiskLevel.LOW))

    assert decision.allowed is False
    assert decision.requires_human is True

