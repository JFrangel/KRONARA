from kronara.training_rights import (
    RightsMode,
    TrainingAsset,
    TrainingRightsPolicy,
)


def test_owned_original_artifact_can_be_used_for_training():
    asset = TrainingAsset(
        asset_id="story-1",
        rights_mode=RightsMode.OWNED_ORIGINAL,
        source_uri="kronara://artifacts/story-1",
    )

    decision = TrainingRightsPolicy().decide(asset, commercial_use=True)

    assert decision.allowed is True
    assert decision.code == "OWNED_ORIGINAL"


def test_licensed_adaptation_requires_evidenced_training_and_commercial_scope():
    asset = TrainingAsset(
        asset_id="adaptation-1",
        rights_mode=RightsMode.LICENSED_ADAPTATION,
        source_uri="https://example.test/source",
        permission_evidence_uri="kronara://rights/license-1",
        allows_training=True,
        allows_commercial=False,
    )

    decision = TrainingRightsPolicy().decide(asset, commercial_use=True)

    assert decision.allowed is False
    assert decision.code == "COMMERCIAL_SCOPE_MISSING"


def test_reference_only_and_permissionless_adaptations_never_enter_training():
    policy = TrainingRightsPolicy()
    reference = TrainingAsset(
        asset_id="reddit-1",
        rights_mode=RightsMode.REFERENCE_ONLY,
        source_uri="https://reddit.com/r/stories/1",
    )
    adaptation = TrainingAsset(
        asset_id="adaptation-2",
        rights_mode=RightsMode.LICENSED_ADAPTATION,
        source_uri="https://reddit.com/r/stories/2",
        allows_training=True,
        allows_commercial=True,
    )

    assert policy.decide(reference).code == "REFERENCE_ONLY"
    assert policy.decide(adaptation).code == "PERMISSION_EVIDENCE_MISSING"
